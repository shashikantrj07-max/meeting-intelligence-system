from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Decision(BaseModel):
    text: str = Field(..., min_length=1)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Decision text must not be empty or whitespace only.")
        return value.strip()


class ActionItem(BaseModel):
    text: str = Field(..., min_length=1)
    owner: Optional[str] = None
    due_date: Optional[str] = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Action item text must not be empty or whitespace only.")
        return value.strip()


class RiskBlocker(BaseModel):
    text: str = Field(..., min_length=1)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Risk or blocker text must not be empty or whitespace only.")
        return value.strip()


class MeetingInsights(BaseModel):
    summary: str = Field(..., min_length=1)
    key_decisions: list[Decision] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    risks_blockers: list[RiskBlocker] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Summary must not be empty or whitespace only.")
        return value.strip()
