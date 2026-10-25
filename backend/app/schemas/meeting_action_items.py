from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


ActionItemStatus = Literal["open", "in_progress", "completed"]
ActionItemAccountabilityFilter = Literal[
    "all",
    "open",
    "in_progress",
    "completed",
    "overdue",
    "needs_attention",
    "follow_up",
]


class ActionItemStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ActionItemStatus


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


class ActionItemAccountabilitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    open: int
    in_progress: int
    completed: int
    overdue: int


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


class ActionItemAccountabilityItemsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ActionItemAccountabilityRecord]
    page: int
    page_size: int
    has_more: bool
