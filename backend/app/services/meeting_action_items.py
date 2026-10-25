from __future__ import annotations

import hashlib
import re
from typing import Any

from app.schemas.meeting_insights import ActionItem


def action_item_identity_key(text: str) -> str:
    normalized_text = re.sub(r"\s+", " ", text).strip().lower()
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def build_tracked_action_item_records(
    meeting_id: str,
    action_items: list[ActionItem],
) -> list[dict[str, str | None]]:
    records: dict[str, dict[str, str | None]] = {}
    for action_item in action_items:
        record = action_item.model_dump(mode="json")
        identity_key = action_item_identity_key(action_item.text)
        records.setdefault(
            identity_key,
            {
                "meeting_id": meeting_id,
                "identity_key": identity_key,
                "text": record["text"],
                "owner": record["owner"],
                "due_date": record["due_date"],
                "priority": record["priority"],
                "evidence": record["evidence"],
            },
        )
    return list(records.values())


def sync_generated_action_items(
    supabase: Any,
    meeting_id: str,
    action_items: list[ActionItem],
) -> None:
    records = build_tracked_action_item_records(meeting_id, action_items)
    if not records:
        return

    (
        supabase.schema("public")
        .table("meeting_action_items")
        .upsert(
            records,
            on_conflict="meeting_id,identity_key",
        )
        .execute()
    )
