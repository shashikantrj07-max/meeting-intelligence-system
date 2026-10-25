from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.routers import meeting_action_items as action_item_router
from app.schemas.meeting_action_items import ActionItemStatusUpdate
from app.schemas.meeting_insights import ActionItem
from app.services.meeting_action_items import (
    action_item_identity_key,
    build_tracked_action_item_records,
    is_action_item_overdue,
    sync_generated_action_items,
)


MEETING_ID = "00000000-0000-0000-0000-000000000001"
ACTION_ITEM_ID = "00000000-0000-0000-0000-000000000002"


class FakeQuery:
    def __init__(self, client: "FakeSupabase", table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.operation = "select"
        self.filters: dict[str, str] = {}
        self.values: dict | list[dict] = {}

    def select(self, _columns: str) -> "FakeQuery":
        return self

    def eq(self, column: str, value: str) -> "FakeQuery":
        self.filters[column] = value
        return self

    def maybe_single(self) -> "FakeQuery":
        return self

    def order(self, _column: str) -> "FakeQuery":
        return self

    def update(self, values: dict) -> "FakeQuery":
        self.operation = "update"
        self.values = values
        return self

    def upsert(self, values: list[dict], **_kwargs: object) -> "FakeQuery":
        self.operation = "upsert"
        self.values = values
        return self

    def execute(self) -> SimpleNamespace:
        if self.table_name == "meetings":
            data = {"id": MEETING_ID} if self.client.meeting_access else None
            return SimpleNamespace(data=data)

        if self.table_name == "meeting_insights":
            return SimpleNamespace(data={"action_items": self.client.generated_items})

        if self.table_name != "meeting_action_items":
            raise AssertionError(f"Unexpected table: {self.table_name}")

        if self.operation == "upsert":
            assert isinstance(self.values, list)
            for values in self.values:
                existing = next(
                    (
                        item
                        for item in self.client.action_items
                        if item["meeting_id"] == values["meeting_id"]
                        and item["identity_key"] == values["identity_key"]
                    ),
                    None,
                )
                if existing:
                    existing.update(values)
                else:
                    self.client.action_items.append(
                        {
                            **values,
                            "id": ACTION_ITEM_ID,
                            "status": "open",
                            "created_at": "2026-10-25T00:00:00Z",
                            "updated_at": "2026-10-25T00:00:00Z",
                        }
                    )
            return SimpleNamespace(data=None)

        matching = [
            item
            for item in self.client.action_items
            if all(item.get(key) == value for key, value in self.filters.items())
        ]
        if self.operation == "update":
            for item in matching:
                assert isinstance(self.values, dict)
                self.client.action_item_updates.append(self.values.copy())
                item.update(self.values)
            return SimpleNamespace(data=matching[0] if matching else None)

        return SimpleNamespace(data=matching)


class FakeRpc:
    def __init__(self, client: "FakeSupabase", function_name: str) -> None:
        self.client = client
        self.function_name = function_name

    def execute(self) -> SimpleNamespace:
        assert self.function_name == "get_my_action_item_accountability_summary"
        self.client.rpc_calls.append(self.function_name)
        today = datetime.now(timezone.utc).date()
        summary = {
            "total": len(self.client.action_items),
            "open": 0,
            "in_progress": 0,
            "completed": 0,
            "overdue": 0,
        }
        for item in self.client.action_items:
            status = item["status"]
            summary[status] += 1
            if is_action_item_overdue(item.get("due_date"), status, today=today):
                summary["overdue"] += 1
        return SimpleNamespace(data=[summary])


class FakeSupabase:
    def __init__(self, *, meeting_access: bool = True) -> None:
        self.meeting_access = meeting_access
        self.generated_items = [
            {
                "text": "Send the draft",
                "owner": "Sam",
                "due_date": "Friday",
                "priority": "high",
                "evidence": "Sam will send the draft by Friday.",
            }
        ]
        self.action_items: list[dict] = []
        self.action_item_updates: list[dict] = []
        self.rpc_calls: list[str] = []
        self.auth = SimpleNamespace(
            get_user=lambda _token: SimpleNamespace(
                user=SimpleNamespace(id="owner-id")
            )
        )

    def schema(self, _name: str) -> "FakeSupabase":
        return self

    def table(self, table_name: str) -> FakeQuery:
        return FakeQuery(self, table_name)

    def rpc(self, function_name: str) -> FakeRpc:
        return FakeRpc(self, function_name)


def make_client(monkeypatch: pytest.MonkeyPatch, supabase: FakeSupabase) -> TestClient:
    monkeypatch.setattr(
        action_item_router,
        "create_request_supabase_client",
        lambda _token: supabase,
    )
    app = FastAPI()
    app.include_router(action_item_router.router)
    return TestClient(app)


def test_status_schema_accepts_only_supported_values() -> None:
    for status in ("open", "in_progress", "completed"):
        assert ActionItemStatusUpdate(status=status).status == status

    with pytest.raises(ValidationError):
        ActionItemStatusUpdate(status="blocked")


def test_action_item_overdue_date_rules() -> None:
    today = date(2026, 10, 25)
    past = (today - timedelta(days=1)).isoformat()
    future = (today + timedelta(days=1)).isoformat()

    assert is_action_item_overdue(past, "open", today=today)
    assert is_action_item_overdue(past, "in_progress", today=today)
    assert not is_action_item_overdue(past, "completed", today=today)
    assert not is_action_item_overdue(today.isoformat(), "open", today=today)
    assert not is_action_item_overdue(future, "open", today=today)
    assert not is_action_item_overdue(None, "open", today=today)
    assert not is_action_item_overdue("", "open", today=today)
    assert not is_action_item_overdue("Friday", "open", today=today)
    assert not is_action_item_overdue("2026-02-30", "open", today=today)
    assert not is_action_item_overdue("20261024", "open", today=today)


def test_identity_and_sync_are_stable_and_preserve_status() -> None:
    action = ActionItem(text="  Send   the draft ", owner="Sam")
    records = build_tracked_action_item_records(
        MEETING_ID,
        [action, ActionItem(text="send the draft")],
    )
    assert len(records) == 1
    assert records[0]["identity_key"] == action_item_identity_key("send the draft")

    supabase = FakeSupabase()
    sync_generated_action_items(supabase, MEETING_ID, [action])
    supabase.action_items[0]["status"] = "completed"

    regenerated_action = ActionItem(
        text="send the draft",
        owner="Taylor",
        due_date="Monday",
    )
    sync_generated_action_items(supabase, MEETING_ID, [regenerated_action])

    assert len(supabase.action_items) == 1
    assert supabase.action_items[0]["status"] == "completed"
    assert supabase.action_items[0]["owner"] == "Taylor"
    assert supabase.action_items[0]["due_date"] == "Monday"


def test_owner_only_access_hides_other_meetings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client(monkeypatch, FakeSupabase(meeting_access=False))

    response = client.get(
        f"/api/meetings/{MEETING_ID}/action-items",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Meeting not found or inaccessible."

    update_response = client.patch(
        f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}",
        headers={"Authorization": "Bearer valid-token"},
        json={"status": "completed"},
    )
    assert update_response.status_code == 404


def test_sync_and_retrieval_return_meeting_action_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client(monkeypatch, FakeSupabase())
    headers = {"Authorization": "Bearer valid-token"}

    synced = client.post(
        f"/api/meetings/{MEETING_ID}/action-items/sync",
        headers=headers,
    )
    retrieved = client.get(
        f"/api/meetings/{MEETING_ID}/action-items",
        headers=headers,
    )

    assert synced.status_code == 200
    assert retrieved.status_code == 200
    assert len(synced.json()["items"]) == 1
    assert retrieved.json()["items"][0]["text"] == "Send the draft"
    assert retrieved.json()["items"][0]["status"] == "open"
    assert retrieved.json()["items"][0]["is_overdue"] is False


def test_accountability_summary_counts_persisted_status_and_overdue_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = datetime.now(timezone.utc).date()
    past_due_date = (today - timedelta(days=1)).isoformat()
    supabase = FakeSupabase()
    supabase.action_items = [
        {"status": "open", "due_date": past_due_date},
        {"status": "open", "due_date": today.isoformat()},
        {"status": "open", "due_date": "not-a-date"},
        {"status": "in_progress", "due_date": past_due_date},
        {"status": "completed", "due_date": past_due_date},
    ]
    supabase.action_items.extend(
        {"status": "completed", "due_date": past_due_date} for _ in range(500)
    )
    client = make_client(monkeypatch, supabase)

    response = client.get(
        "/api/meetings/action-items/accountability-summary",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "total": 505,
        "open": 3,
        "in_progress": 1,
        "completed": 501,
        "overdue": 2,
    }
    assert supabase.rpc_calls == ["get_my_action_item_accountability_summary"]


def test_action_item_status_update_is_scoped_to_meeting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase = FakeSupabase()
    sync_generated_action_items(
        supabase,
        MEETING_ID,
        [ActionItem(text="Send the draft")],
    )
    client = make_client(monkeypatch, supabase)

    invalid_response = client.patch(
        f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}",
        headers={"Authorization": "Bearer valid-token"},
        json={"status": "blocked"},
    )
    response = client.patch(
        f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}",
        headers={"Authorization": "Bearer valid-token"},
        json={"status": "in_progress"},
    )

    assert invalid_response.status_code == 422
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    assert UUID(response.json()["meeting_id"]) == UUID(MEETING_ID)
    assert supabase.action_item_updates == [{"status": "in_progress"}]
