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
    def __init__(
        self,
        client: "FakeSupabase",
        function_name: str,
        params: dict | None,
    ) -> None:
        self.client = client
        self.function_name = function_name
        self.params = params

    def execute(self) -> SimpleNamespace:
        self.client.rpc_calls.append(self.function_name)
        today = datetime.now(timezone.utc).date()
        if self.function_name == "get_my_action_item_accountability_summary":
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

        assert self.function_name == "get_my_action_item_accountability_items"
        assert self.params is not None
        self.client.rpc_arguments.append((self.function_name, self.params))
        requested_status = self.params["p_status"]
        offset = self.params["p_offset"]
        rows = []
        for item in self.client.action_items:
            parsed_due_date = None
            due_date = item.get("due_date")
            if isinstance(due_date, str):
                try:
                    parsed_due_date = date.fromisoformat(due_date)
                    if parsed_due_date.isoformat() != due_date:
                        parsed_due_date = None
                except ValueError:
                    parsed_due_date = None
            overdue = is_action_item_overdue(
                due_date,
                item["status"],
                today=today,
            )
            if item["status"] == "completed":
                attention_reason = "completed"
                urgency_rank = 4
            elif overdue:
                attention_reason = "overdue"
                urgency_rank = 0
            elif parsed_due_date is not None and parsed_due_date <= today + timedelta(days=7):
                attention_reason = "due_soon"
                urgency_rank = 1
            elif parsed_due_date is not None:
                attention_reason = "due_later"
                urgency_rank = 2
            else:
                attention_reason = "no_usable_due_date"
                urgency_rank = 3

            if item["status"] == "completed":
                follow_up_reason = None
                follow_up_rank = 6
            elif overdue:
                follow_up_reason = "overdue"
                follow_up_rank = 0
            elif parsed_due_date == today:
                follow_up_reason = "due_today"
                follow_up_rank = 1
            elif parsed_due_date is not None and parsed_due_date <= today + timedelta(days=7):
                follow_up_reason = "due_soon"
                follow_up_rank = 2
            elif (item.get("priority") or "").lower() in {"urgent", "high"}:
                follow_up_reason = "high_priority"
                follow_up_rank = 3
            elif parsed_due_date is None:
                follow_up_reason = "missing_due_date"
                follow_up_rank = 4
            else:
                follow_up_reason = "due_later"
                follow_up_rank = 5
            if requested_status == "all":
                matches = True
            elif requested_status == "overdue":
                matches = overdue
            elif requested_status == "needs_attention":
                matches = item["status"] != "completed"
            elif requested_status == "follow_up":
                matches = item["status"] != "completed"
            else:
                matches = item["status"] == requested_status
            if matches:
                rows.append(
                    {
                        "id": item["id"],
                        "meeting_id": item["meeting_id"],
                        "meeting_title": item["meeting_title"],
                        "text": item["text"],
                        "owner": item.get("owner"),
                        "due_date": due_date,
                        "priority": item.get("priority"),
                        "status": item["status"],
                        "is_overdue": overdue,
                        "attention_reason": attention_reason,
                        "follow_up_reason": follow_up_reason,
                        "urgency_rank": urgency_rank,
                        "follow_up_rank": follow_up_rank,
                        "priority_rank": {
                            "urgent": 0,
                            "high": 1,
                            "medium": 2,
                            "low": 3,
                        }.get((item.get("priority") or "").lower(), 4),
                        "status_rank": {
                            "open": 0,
                            "in_progress": 1,
                        }.get(item["status"], 2),
                        "created_at": item.get("created_at", "2026-10-25T00:00:00Z"),
                        "parsed_due_date": parsed_due_date,
                    }
                )
        if requested_status == "follow_up":
            rows.sort(
                key=lambda row: (
                    row["follow_up_rank"],
                    row["priority_rank"],
                    row["status_rank"],
                    row["parsed_due_date"] or date.max,
                    -datetime.fromisoformat(
                        row["created_at"].replace("Z", "+00:00")
                    ).timestamp(),
                    row["id"],
                )
            )
        else:
            rows.sort(
                key=lambda row: (
                    row["urgency_rank"],
                    row["parsed_due_date"]
                    if row["urgency_rank"] in (0, 1, 2)
                    else date.max,
                    row["priority_rank"],
                    row["status_rank"],
                    -datetime.fromisoformat(
                        row["created_at"].replace("Z", "+00:00")
                    ).timestamp(),
                    row["id"],
                )
            )
        rows = [
            {
                key: value
                for key, value in row.items()
                if key
                not in {
                    "urgency_rank",
                    "follow_up_rank",
                    "priority_rank",
                    "status_rank",
                    "created_at",
                    "parsed_due_date",
                }
            }
            for row in rows
        ]
        return SimpleNamespace(data=rows[offset : offset + 26])


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
        self.rpc_arguments: list[tuple[str, dict]] = []
        self.verified_tokens: list[str] = []

        def get_user(token: str) -> SimpleNamespace:
            self.verified_tokens.append(token)
            return SimpleNamespace(user=SimpleNamespace(id="owner-id"))

        self.auth = SimpleNamespace(get_user=get_user)

    def schema(self, _name: str) -> "FakeSupabase":
        return self

    def table(self, table_name: str) -> FakeQuery:
        return FakeQuery(self, table_name)

    def rpc(self, function_name: str, params: dict | None = None) -> FakeRpc:
        return FakeRpc(self, function_name, params)


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


def test_accountability_items_require_auth_and_validate_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase = FakeSupabase()
    client = make_client(monkeypatch, supabase)

    unauthenticated = client.get(
        "/api/meetings/action-items/accountability-items?status=open",
    )
    unauthenticated_follow_up = client.get(
        "/api/meetings/action-items/accountability-items?status=follow_up",
    )
    invalid_filter = client.get(
        "/api/meetings/action-items/accountability-items?status=blocked",
        headers={"Authorization": "Bearer test-token"},
    )

    assert unauthenticated.status_code == 401
    assert unauthenticated_follow_up.status_code == 401
    assert invalid_filter.status_code == 422
    assert supabase.rpc_arguments == []


def test_accountability_filters_match_summary_and_overdue_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = datetime.now(timezone.utc).date()
    past = (today - timedelta(days=1)).isoformat()
    future = (today + timedelta(days=1)).isoformat()
    due_items = [
        ("open-past", "open", past),
        ("progress-past", "in_progress", past),
        ("completed-past", "completed", past),
        ("open-today", "open", today.isoformat()),
        ("open-future", "open", future),
        ("open-invalid", "open", "2026-02-30"),
        ("open-freeform", "open", "Friday"),
        ("open-missing", "open", None),
    ]
    supabase = FakeSupabase()
    supabase.action_items = [
        {
            "id": f"00000000-0000-0000-0000-{index:012d}",
            "meeting_id": MEETING_ID,
            "meeting_title": "Planning",
            "text": text,
            "owner": None,
            "due_date": due_date,
            "status": status,
        }
        for index, (text, status, due_date) in enumerate(due_items, start=1)
    ]
    client = make_client(monkeypatch, supabase)
    headers = {"Authorization": "Bearer test-token"}

    expected = {
        "all": 8,
        "open": 6,
        "in_progress": 1,
        "completed": 1,
        "overdue": 2,
        "follow_up": 7,
    }
    responses = {
        filter_value: client.get(
            "/api/meetings/action-items/accountability-items",
            params={"status": filter_value},
            headers=headers,
        )
        for filter_value in expected
    }

    for filter_value, count in expected.items():
        response = responses[filter_value]
        assert response.status_code == 200, response.text
        assert len(response.json()["items"]) == count

    overdue_items = responses["overdue"].json()["items"]
    assert {item["text"] for item in overdue_items} == {
        "open-past",
        "progress-past",
    }
    assert all(item["is_overdue"] for item in overdue_items)
    all_items = {
        item["text"]: item
        for item in responses["all"].json()["items"]
    }
    assert all_items["completed-past"]["is_overdue"] is False
    assert all_items["open-today"]["is_overdue"] is False
    assert all_items["open-future"]["is_overdue"] is False
    assert all_items["open-invalid"]["is_overdue"] is False
    assert all_items["open-freeform"]["is_overdue"] is False
    assert all_items["open-missing"]["is_overdue"] is False

    summary = client.get(
        "/api/meetings/action-items/accountability-summary",
        headers=headers,
    )
    assert summary.status_code == 200
    assert summary.json()["overdue"] == len(overdue_items)
    assert all(
        "user_id" not in parameters
        for _, parameters in supabase.rpc_arguments
    )
    assert all(
        function_name == "get_my_action_item_accountability_items"
        for function_name, _ in supabase.rpc_arguments
    )
    assert supabase.verified_tokens == ["test-token"] * (
        len(expected) + 1
    )
    assert all(
        set(parameters) == {"p_status", "p_offset"}
        for _, parameters in supabase.rpc_arguments
    )


def test_accountability_items_are_paginated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase = FakeSupabase()
    supabase.action_items = [
        {
            "id": f"00000000-0000-0000-0000-{index:012d}",
            "meeting_id": MEETING_ID,
            "meeting_title": "Planning",
            "text": f"Task {index}",
            "owner": None,
            "due_date": None,
            "status": "open",
        }
        for index in range(1, 28)
    ]
    client = make_client(monkeypatch, supabase)
    headers = {"Authorization": "Bearer test-token"}

    first = client.get(
        "/api/meetings/action-items/accountability-items?status=follow_up",
        headers=headers,
    )
    second = client.get(
        "/api/meetings/action-items/accountability-items?status=follow_up&page=2",
        headers=headers,
    )

    assert first.status_code == second.status_code == 200
    assert len(first.json()["items"]) == 25
    assert first.json()["has_more"] is True
    assert len(second.json()["items"]) == 2
    assert second.json()["has_more"] is False
    assert second.json()["page"] == 2


def test_follow_up_classifies_and_orders_unresolved_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = datetime.now(timezone.utc).date()
    fixtures = [
        ("overdue-low", "open", (today - timedelta(days=2)).isoformat(), "low"),
        ("overdue-high", "open", (today - timedelta(days=1)).isoformat(), "high"),
        ("due-today-low", "open", today.isoformat(), "low"),
        ("due-soon-later-high", "open", (today + timedelta(days=7)).isoformat(), "high"),
        ("due-soon-earlier-low", "open", (today + timedelta(days=2)).isoformat(), "low"),
        ("priority-later-urgent", "open", (today + timedelta(days=12)).isoformat(), "urgent"),
        ("priority-missing-high", "open", None, "high"),
        ("missing-malformed-progress", "in_progress", "2026-02-30", "low"),
        ("missing-freeform-open", "open", "Friday", "low"),
        ("missing-null-open", "open", None, "low"),
        ("later-medium", "open", (today + timedelta(days=8)).isoformat(), "medium"),
        ("completed-overdue", "completed", (today - timedelta(days=1)).isoformat(), "urgent"),
    ]
    supabase = FakeSupabase()
    supabase.action_items = [
        {
            "id": f"00000000-0000-0000-0000-{index:012d}",
            "meeting_id": MEETING_ID,
            "meeting_title": "Planning",
            "text": text,
            "owner": "Sam",
            "due_date": due_date,
            "priority": priority,
            "status": status,
            "created_at": "2026-10-25T00:00:00Z",
        }
        for index, (text, status, due_date, priority) in enumerate(fixtures, start=1)
    ]
    client = make_client(monkeypatch, supabase)

    response = client.get(
        "/api/meetings/action-items/accountability-items",
        params={"status": "follow_up"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["text"] for item in items] == [
        "overdue-high",
        "overdue-low",
        "due-today-low",
        "due-soon-later-high",
        "due-soon-earlier-low",
        "priority-later-urgent",
        "priority-missing-high",
        "missing-freeform-open",
        "missing-null-open",
        "missing-malformed-progress",
        "later-medium",
    ]
    assert [item["follow_up_reason"] for item in items] == [
        "overdue",
        "overdue",
        "due_today",
        "due_soon",
        "due_soon",
        "high_priority",
        "high_priority",
        "missing_due_date",
        "missing_due_date",
        "missing_due_date",
        "due_later",
    ]
    assert all(item["status"] != "completed" for item in items)
    assert supabase.verified_tokens == ["test-token"]
    assert supabase.rpc_arguments == [
        (
            "get_my_action_item_accountability_items",
            {"p_status": "follow_up", "p_offset": 0},
        )
    ]
    assert "user_id" not in supabase.rpc_arguments[0][1]


def test_needs_attention_is_prioritized_deterministically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = datetime.now(timezone.utc).date()
    fixtures = [
        ("overdue-older", "open", (today - timedelta(days=2)).isoformat(), "low"),
        ("overdue-urgent", "in_progress", (today - timedelta(days=1)).isoformat(), "urgent"),
        ("due-today-low", "open", today.isoformat(), "low"),
        ("due-today-high", "open", today.isoformat(), "high"),
        ("due-seven", "open", (today + timedelta(days=7)).isoformat(), "medium"),
        ("due-eight", "open", (today + timedelta(days=8)).isoformat(), "urgent"),
        ("invalid-open", "open", "2026-02-30", None),
        ("missing-open", "open", None, None),
        ("missing-progress", "in_progress", None, None),
        ("completed-overdue", "completed", (today - timedelta(days=3)).isoformat(), "urgent"),
    ]
    supabase = FakeSupabase()
    supabase.action_items = [
        {
            "id": f"00000000-0000-0000-0000-{index:012d}",
            "meeting_id": MEETING_ID,
            "meeting_title": "Planning",
            "text": text,
            "owner": None,
            "due_date": due_date,
            "priority": priority,
            "status": status,
            "created_at": "2026-10-25T00:00:00Z",
        }
        for index, (text, status, due_date, priority) in enumerate(fixtures, start=1)
    ]
    client = make_client(monkeypatch, supabase)

    response = client.get(
        "/api/meetings/action-items/accountability-items",
        params={"status": "needs_attention"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["text"] for item in items] == [
        "overdue-older",
        "overdue-urgent",
        "due-today-high",
        "due-today-low",
        "due-seven",
        "due-eight",
        "invalid-open",
        "missing-open",
        "missing-progress",
    ]
    assert [item["attention_reason"] for item in items] == [
        "overdue",
        "overdue",
        "due_soon",
        "due_soon",
        "due_soon",
        "due_later",
        "no_usable_due_date",
        "no_usable_due_date",
        "no_usable_due_date",
    ]
    assert all(item["status"] != "completed" for item in items)
    assert items[0]["priority"] == "low"
    assert items[1]["priority"] == "urgent"
    assert items[2]["priority"] == "high"


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
