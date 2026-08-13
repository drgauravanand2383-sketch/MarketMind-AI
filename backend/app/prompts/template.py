"""PromptTemplate — a single, versioned, immutable prompt definition.

No rendering logic and no reasoning live here — `PromptTemplate` is a pure
data holder ("metadata only"); `PromptRenderer` performs all actual
variable substitution. The one piece of behavior this module owns is
validating, at construction time, that every `{placeholder}` in
`system_prompt`/`user_prompt` is a simple named variable — `{name}`,
optionally with a format spec/conversion like `{name:>10}` or `{name!r}`
— and rejecting anything else (unnamed `{}`, positional `{0}`,
attribute/index access `{a.b}`) as an unsupported placeholder shape.
"""

from __future__ import annotations

import string

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.prompts.exceptions import TemplateValidationError
from app.prompts.models import PromptMetadata

__all__ = ["PromptTemplate"]

_FORMATTER = string.Formatter()


def _extract_placeholders(text: str) -> frozenset[str]:
    """Return every valid named placeholder in `text`.

    Raises:
        TemplateValidationError: If `text` contains a placeholder that
            isn't a simple named identifier.
    """
    names: set[str] = set()
    for _literal, field_name, _format_spec, _conversion in _FORMATTER.parse(text):
        if field_name is None:
            continue
        if not field_name.isidentifier():
            raise TemplateValidationError(
                f"Unsupported placeholder {{{field_name}}} — only simple named variables "
                "like {variable_name} are supported (no positional, unnamed, or "
                "attribute/index-access placeholders)."
            )
        names.add(field_name)
    return frozenset(names)


class PromptTemplate(BaseModel):
    """A single, versioned, immutable prompt definition.

    `required_variables` is derived from `system_prompt`/`user_prompt`,
    never independently declared — this guarantees it can never drift out
    of sync with what the template text actually references.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: int = Field(ge=1)
    description: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    user_prompt: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_placeholders(self) -> PromptTemplate:
        """Fail fast at construction if either prompt has an unsupported placeholder."""
        _extract_placeholders(self.system_prompt)
        _extract_placeholders(self.user_prompt)
        return self

    @property
    def required_variables(self) -> frozenset[str]:
        """Every named variable referenced in `system_prompt` or `user_prompt`."""
        return _extract_placeholders(self.system_prompt) | _extract_placeholders(self.user_prompt)

    @property
    def metadata(self) -> PromptMetadata:
        """A content-free summary of this template."""
        return PromptMetadata(
            template_id=self.template_id,
            name=self.name,
            version=self.version,
            description=self.description,
            required_variables=tuple(sorted(self.required_variables)),
        )
