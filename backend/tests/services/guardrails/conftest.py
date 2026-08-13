"""Shared schemas for Guardrails Framework tests. Real Pydantic models
throughout — nothing in this package is mocked."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Address(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: str
    zip_code: str


class Person(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    age: int
    address: Address
