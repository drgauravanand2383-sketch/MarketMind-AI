"""Shared factories for Prompt Template Framework tests."""

from __future__ import annotations

from app.prompts.template import PromptTemplate


def build_template(
    template_id: str = "company_research",
    name: str = "Company Research",
    version: int = 1,
    description: str = "Research a company",
    system_prompt: str = "You are a research assistant.",
    user_prompt: str = "Research the company {company_name} in the {sector} sector.",
) -> PromptTemplate:
    return PromptTemplate(
        template_id=template_id,
        name=name,
        version=version,
        description=description,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
