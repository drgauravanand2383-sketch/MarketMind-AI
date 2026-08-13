"""StructuredOutputParser — safely parses raw LLM response text into a Python object.

No AI calls, no schema validation, no repository logic. This module only
repairs and parses raw text; `app.services.guardrails.validator` does all
schema-level work. Repair is intentionally limited to three safe,
content-preserving transformations (see `_repair()`): trimming a markdown
code fence, trimming leading/trailing whitespace, and normalizing line
endings. Nothing here ever invents a missing value or infers a missing
field — repair only ever removes formatting noise around content the LLM
already produced; anything beyond that (e.g. a trailing comma, an unquoted
key) is left as a genuine parse error, not silently "fixed."
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.guardrails.exceptions import RepairError
from app.services.guardrails.models import ParseOutcome

__all__ = ["StructuredOutputParser"]

_CODE_FENCE_PATTERN = re.compile(r"^```[a-zA-Z0-9_-]*[ \t]*\n?(.*?)\n?```$", re.DOTALL)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """An `object_pairs_hook` for `json.loads()` that raises on a duplicate
    key within any single JSON object, at any nesting depth.

    `json.loads()`'s own default behavior silently keeps the last
    occurrence of a duplicate key — too permissive for LLM output, where a
    duplicate key is a sign of a malformed generation, not a legitimate
    "override."
    """
    seen: set[str] = set()
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"Duplicate key {key!r} in JSON object")
        seen.add(key)
        result[key] = value
    return result


class StructuredOutputParser:
    """Repairs and parses raw text into a Python object.

    No singleton, no global state: construct one instance and inject it
    wherever parsing is needed (e.g. into `OutputValidator`).
    """

    def parse(self, raw_response: str, *, reject_duplicate_keys: bool = True) -> ParseOutcome:
        """Repair `raw_response` (safely) and parse it as JSON.

        Args:
            raw_response: The raw text to parse — typically an LLM's response content.
            reject_duplicate_keys: If True (default), a duplicate key
                anywhere in the JSON is treated as malformed input rather
                than silently keeping the last occurrence.

        Returns:
            A ParseOutcome. `error` is set (and `value` is `None`) if the
            repaired text still isn't valid JSON — this method itself
            never raises for malformed input. Only `RepairError` (a
            genuinely unexpected failure in the repair step, e.g. a
            non-string `raw_response`) can raise.
        """
        if not isinstance(raw_response, str):
            raise RepairError(f"raw_response must be a string, got {type(raw_response).__name__}")

        try:
            text, repaired, warnings = self._repair(raw_response)
        except RepairError:
            raise
        except Exception as exc:  # noqa: BLE001 - an unexpected repair-step failure must not leak raw
            raise RepairError(f"Unexpected failure while repairing raw_response: {exc}") from exc

        try:
            if reject_duplicate_keys:
                value = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
            else:
                value = json.loads(text)
        except ValueError as exc:
            return ParseOutcome(value=None, repaired=repaired, warnings=warnings, error=str(exc))

        return ParseOutcome(value=value, repaired=repaired, warnings=warnings, error=None)

    def _repair(self, raw: str) -> tuple[str, bool, list[str]]:
        """Apply only the three sanctioned repairs. Never invents or infers content.

        Returns:
            (repaired_text, whether anything was repaired, human-readable
            warnings describing exactly what was repaired).
        """
        text = raw
        warnings: list[str] = []
        repaired = False

        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        if normalized != text:
            warnings.append("Normalized line endings.")
            repaired = True
            text = normalized

        stripped = text.strip()
        if stripped != text:
            warnings.append("Trimmed leading/trailing whitespace.")
            repaired = True
            text = stripped

        fence_match = _CODE_FENCE_PATTERN.match(text)
        if fence_match:
            text = fence_match.group(1).strip()
            warnings.append("Trimmed markdown code fence.")
            repaired = True

        return text, repaired, warnings
