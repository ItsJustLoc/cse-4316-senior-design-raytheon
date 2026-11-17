"""Shared JSON schema and runtime validation for proposed missions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Target(StrictModel):
    color: Literal[
        "red", "orange", "yellow", "green", "blue", "purple",
        "pink", "brown", "black", "white", "gray",
    ]
    object_type: Literal["cube", "box", "ball", "object"]


class Mission(StrictModel):
    action: Literal["retrieve", "read_nfc", "return_to_start", "stop"]
    target: Target | None

    @model_validator(mode="after")
    def check_target(self) -> Mission:
        needs_target = self.action in ("retrieve", "read_nfc")
        if needs_target != (self.target is not None):
            raise ValueError("Only retrieve and read_nfc require a target.")
        return self


class Interpretation(StrictModel):
    status: Literal["ready", "clarification_required", "rejected"]
    mission: Mission | None
    message: str = Field(min_length=1, max_length=500)

    @field_validator("message")
    @classmethod
    def check_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("An explanation or clarification question is required.")
        return value

    @model_validator(mode="after")
    def check_status(self) -> Interpretation:
        if (self.status == "ready") != (self.mission is not None):
            raise ValueError("Only a ready interpretation must contain a mission.")
        return self


class ParsedIntent(StrictModel):
    schema_version: Literal[1] = 1
    original_text: str
    interpretation: Interpretation
