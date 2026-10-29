from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ActionItemStatus = Literal["open", "in_progress", "completed"]
ActionItemAccountabilitySignal = Literal[
    "reopened",
    "repeated_updates",
    "stale",
    "recent_activity",
]
ActionItemAccountabilityFilter = Literal[
    "all",
    "open",
    "in_progress",
    "completed",
    "overdue",
    "needs_attention",
    "follow_up",
    "reopened",
    "repeated_updates",
    "stale",
    "recent_activity",
    "needs_review",
]
ActionItemReviewState = Literal[
    "all",
    "reviewable",
    "reviewed",
    "needs_review",
    "reopened_since_review",
]


class ActionItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ActionItemStatus | None = None
    owner: str | None = Field(default=None, max_length=200)
    due_date: str | None = Field(default=None, max_length=100)
    priority: str | None = Field(default=None, max_length=100)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: ActionItemStatus | None) -> ActionItemStatus:
        if value is None:
            raise ValueError("Action-item status cannot be null.")
        return value

    @field_validator("owner", "due_date", "priority", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def require_update_fields(self) -> "ActionItemUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one action-item field must be provided.")
        return self


class TrackedActionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    meeting_id: UUID
    identity_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    text: str = Field(min_length=1)
    owner: str | None = None
    due_date: str | None = None
    priority: str | None = None
    evidence: str | None = None
    status: ActionItemStatus
    is_overdue: bool
    created_at: str
    updated_at: str


class TrackedActionItemsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[TrackedActionItem]


class ActionItemHistoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    action_item_id: UUID
    meeting_id: UUID
    action_item_text: str = Field(min_length=1)
    field_changed: Literal["status", "owner", "due_date", "priority"]
    previous_value: str | None = None
    new_value: str | None = None
    changed_at: datetime


class ActionItemHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ActionItemHistoryRecord]
    accountability_signals: list[ActionItemAccountabilitySignal]
    reviewed_at: datetime | None
    needs_review: bool


class ActionItemAccountabilitySignals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accountability_signals: list[ActionItemAccountabilitySignal]


class ActionItemSignalReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewed_at: datetime
    needs_review: Literal[False]


class ActionItemSignalReviewState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewed_at: datetime | None
    needs_review: bool


class ActionItemAccountabilitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    open: int
    in_progress: int
    completed: int
    overdue: int


class ActionItemReviewAnalytics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_reviewable: int = Field(strict=True, ge=0)
    reviewed: int = Field(strict=True, ge=0)
    needs_review: int = Field(strict=True, ge=0)
    reopened_since_review: int = Field(strict=True, ge=0)
    review_coverage_percent: float = Field(strict=True, ge=0, le=100)

    @field_validator("review_coverage_percent")
    @classmethod
    def validate_coverage_precision(cls, value: float) -> float:
        if Decimal(str(value)).as_tuple().exponent < -1:
            raise ValueError("Review coverage must use at most one decimal place.")
        return value

    @model_validator(mode="after")
    def validate_counts(self) -> "ActionItemReviewAnalytics":
        if self.reviewed + self.needs_review != self.total_reviewable:
            raise ValueError("Review totals must match the reviewable total.")
        if self.reopened_since_review > self.needs_review:
            raise ValueError(
                "Items reopened since review cannot exceed items needing review."
            )
        if self.total_reviewable == 0 and self.review_coverage_percent != 0:
            raise ValueError("Coverage must be zero when there are no reviewable items.")
        return self


class ActionItemAccountabilityRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    meeting_id: UUID
    meeting_title: str
    text: str = Field(min_length=1)
    owner: str | None = None
    due_date: str | None = None
    priority: str | None = None
    status: ActionItemStatus
    is_overdue: bool
    attention_reason: Literal[
        "overdue",
        "due_soon",
        "due_later",
        "no_usable_due_date",
        "completed",
    ]
    follow_up_reason: Literal[
        "overdue",
        "due_today",
        "due_soon",
        "high_priority",
        "missing_due_date",
        "due_later",
    ] | None
    accountability_signals: list[ActionItemAccountabilitySignal]
    reviewed_at: datetime | None
    needs_review: bool


class ActionItemAccountabilityItemsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ActionItemAccountabilityRecord]
    page: int
    page_size: int
    has_more: bool
