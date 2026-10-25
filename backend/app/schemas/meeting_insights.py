from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)
    evidence: Optional[str] = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Decision text must not be empty or whitespace only.")
        return value.strip()


class ActionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)
    owner: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = None
    evidence: Optional[str] = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Action item text must not be empty or whitespace only.")
        return value.strip()


class RiskBlocker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)
    evidence: Optional[str] = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Risk or blocker text must not be empty or whitespace only.")
        return value.strip()


class DiscussionPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)
    evidence: Optional[str] = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError(
                "Discussion point text must not be empty or whitespace only."
            )
        return value.strip()


class OpenQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)
    evidence: Optional[str] = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError(
                "Open question text must not be empty or whitespace only."
            )
        return value.strip()


class NextStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)
    evidence: Optional[str] = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError(
                "Next step text must not be empty or whitespace only."
            )
        return value.strip()


class MeetingInsights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(..., min_length=1)
    key_decisions: list[Decision] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    risks_blockers: list[RiskBlocker] = Field(default_factory=list)
    discussion_points: list[DiscussionPoint] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    next_steps: list[NextStep] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Summary must not be empty or whitespace only.")
        return value.strip()
