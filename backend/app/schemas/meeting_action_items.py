from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


ActionItemStatus = Literal["open", "in_progress", "completed"]


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
    created_at: str
    updated_at: str


class TrackedActionItemsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[TrackedActionItem]
