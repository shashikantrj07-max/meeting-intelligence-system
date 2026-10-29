from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.routers import meeting_action_items as action_item_router
from app.schemas.meeting_action_items import (
    ActionItemAccountabilityRecord,
    ActionItemReviewAnalytics,
    ActionItemUpdate,
    TrackedActionItem,
)
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
        self.orders: list[tuple[str, bool]] = []
        self.single = False

    def select(self, _columns: str) -> "FakeQuery":
        return self

    def eq(self, column: str, value: str) -> "FakeQuery":
        self.filters[column] = value
        return self

    def maybe_single(self) -> "FakeQuery":
        self.single = True
        return self

    def order(self, column: str, desc: bool = False) -> "FakeQuery":
        self.orders.append((column, desc))
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

        if self.table_name == "meeting_action_item_history":
            matching_history = [
                item
                for item in self.client.action_item_history
                if all(
                    item.get(key) == value
                    for key, value in self.filters.items()
                )
            ]
            for column, descending in reversed(self.orders):
                matching_history.sort(
                    key=lambda item: item[column],
                    reverse=descending,
                )
            return SimpleNamespace(data=matching_history)

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
                for field in ("status", "owner", "due_date", "priority"):
                    previous_value = item.get(field)
                    new_value = self.values.get(field, previous_value)
                    if previous_value != new_value:
                        changed_at = (
                            datetime(2026, 10, 27, tzinfo=timezone.utc)
                            + timedelta(seconds=len(self.client.action_item_history))
                        )
                        self.client.action_item_history.append(
                            {
                                "id": (
                                    "00000000-0000-0000-0000-"
                                    f"{len(self.client.action_item_history) + 10:012d}"
                                ),
                                "action_item_id": item["id"],
                                "meeting_id": item["meeting_id"],
                                "action_item_text": item["text"],
                                "field_changed": field,
                                "previous_value": previous_value,
                                "new_value": new_value,
                                "changed_at": changed_at.isoformat(),
                            }
                        )
                item.update(self.values)
            return SimpleNamespace(data=matching[0] if matching else None)

        if self.single:
            return SimpleNamespace(data=matching[0] if matching else None)
        return SimpleNamespace(data=matching)


def fake_accountability_signals(
    item: dict,
    history: list[dict],
) -> list[str]:
    reopened = any(
        entry["field_changed"] == "status"
        and entry["previous_value"] == "completed"
        and entry["new_value"] in {"open", "in_progress"}
        for entry in history
    )
    recent_activity = any(
        datetime.fromisoformat(entry["changed_at"].replace("Z", "+00:00"))
        >= datetime.now(timezone.utc) - timedelta(days=7)
        for entry in history
    )
    signals = []
    if reopened:
        signals.append("reopened")
    if len(history) >= 2:
        signals.append("repeated_updates")
    if item["status"] != "completed" and history:
        signals.append("stale")
    if recent_activity:
        signals.append("recent_activity")
    return signals


def fake_signal_review_state(
    history: list[dict],
    reviewed_state: dict | None,
    signals: list[str],
) -> dict:
    latest_activity = max(
        (
            datetime.fromisoformat(entry["changed_at"].replace("Z", "+00:00"))
            for entry in history
        ),
        default=None,
    )
    reviewed_through = (
        datetime.fromisoformat(
            reviewed_state["reviewed_through"].replace("Z", "+00:00")
        )
        if reviewed_state
        else None
    )
    return {
        "reviewed_at": reviewed_state["reviewed_at"] if reviewed_state else None,
        "needs_review": bool(signals)
        and (
            reviewed_through is None
            or latest_activity is not None
            and latest_activity > reviewed_through
        ),
    }


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
        if self.function_name == "get_my_action_item_review_analytics":
            self.client.rpc_arguments.append((self.function_name, self.params))
            if self.client.review_analytics_error:
                raise RuntimeError("internal analytics database detail")
            if self.client.review_analytics_data is not None:
                return SimpleNamespace(data=self.client.review_analytics_data)
            reviewable = []
            for item in self.client.action_items:
                history = [
                    entry
                    for entry in self.client.action_item_history
                    if entry["action_item_id"] == item.get("id")
                ]
                signals = fake_accountability_signals(item, history)
                if not signals:
                    continue
                review_state = fake_signal_review_state(
                    history,
                    self.client.action_item_signal_reviews.get(item["id"]),
                    signals,
                )
                reviewable.append((review_state, history))
            total_reviewable = len(reviewable)
            needs_review = sum(
                review_state["needs_review"]
                for review_state, _history in reviewable
            )
            reviewed = total_reviewable - needs_review
            reopened_since_review = sum(
                review_state["needs_review"]
                and self.client.action_item_signal_reviews.get(
                    history[0]["action_item_id"]
                )
                is not None
                for review_state, history in reviewable
            )
            coverage = (
                round(reviewed * 100 / total_reviewable, 1)
                if total_reviewable
                else 0
            )
            return SimpleNamespace(
                data=[
                    {
                        "total_reviewable": total_reviewable,
                        "reviewed": reviewed,
                        "needs_review": needs_review,
                        "reopened_since_review": reopened_since_review,
                        "review_coverage_percent": coverage,
                    }
                ]
            )

        if self.function_name == "get_my_action_item_accountability_summary":
            self.client.rpc_arguments.append((self.function_name, self.params))
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

        if self.function_name == "get_my_action_item_accountability_signals":
            assert self.params is not None
            self.client.rpc_arguments.append((self.function_name, self.params))
            if self.client.invalid_signal_result:
                return SimpleNamespace(
                    data=[{"accountability_signals": ["invented"]}]
                )
            action_item_id = self.params["p_action_item_id"]
            item = next(
                (
                    candidate
                    for candidate in self.client.action_items
                    if candidate["id"] == action_item_id
                    and self.client.meeting_access
                ),
                None,
            )
            if item is None:
                return SimpleNamespace(data=[{"accountability_signals": []}])
            history = [
                entry
                for entry in self.client.action_item_history
                if entry["action_item_id"] == action_item_id
            ]
            return SimpleNamespace(
                data=[
                    {
                        "accountability_signals": fake_accountability_signals(
                            item,
                            history,
                        )
                    }
                ]
            )

        if self.function_name == "get_my_action_item_signal_review_state":
            assert self.params is not None
            self.client.rpc_arguments.append((self.function_name, self.params))
            action_item_id = self.params["p_action_item_id"]
            item = next(
                (
                    candidate
                    for candidate in self.client.action_items
                    if candidate["id"] == action_item_id
                    and self.client.meeting_access
                ),
                None,
            )
            if item is None:
                return SimpleNamespace(data=[])
            history = [
                entry
                for entry in self.client.action_item_history
                if entry["action_item_id"] == action_item_id
            ]
            signals = fake_accountability_signals(item, history)
            state = fake_signal_review_state(
                history,
                self.client.action_item_signal_reviews.get(action_item_id),
                signals,
            )
            return SimpleNamespace(data=[state])

        if self.function_name == "review_my_action_item_signals":
            assert self.params is not None
            self.client.rpc_arguments.append((self.function_name, self.params))
            if self.client.invalid_review_result:
                return SimpleNamespace(
                    data=[
                        {
                            "reviewed_at": datetime.now(timezone.utc).isoformat(),
                            "needs_review": True,
                        }
                    ]
                )
            action_item_id = self.params["p_action_item_id"]
            item = next(
                (
                    candidate
                    for candidate in self.client.action_items
                    if candidate["id"] == action_item_id
                    and candidate["meeting_id"] == self.params["p_meeting_id"]
                    and self.client.meeting_access
                ),
                None,
            )
            if item is None:
                return SimpleNamespace(data=[])
            history = [
                entry
                for entry in self.client.action_item_history
                if entry["action_item_id"] == action_item_id
            ]
            signals = fake_accountability_signals(item, history)
            if not signals or not history:
                return SimpleNamespace(data=[])
            latest = max(
                datetime.fromisoformat(
                    entry["changed_at"].replace("Z", "+00:00")
                )
                for entry in history
            )
            reviewed_at = datetime.now(timezone.utc).isoformat()
            review_state = {
                "reviewed_at": reviewed_at,
                "reviewed_through": latest.isoformat(),
            }
            self.client.action_item_signal_reviews[action_item_id] = review_state
            return SimpleNamespace(
                data=[{"reviewed_at": reviewed_at, "needs_review": False}]
            )

        assert self.function_name == "get_my_action_item_accountability_items"
        assert self.params is not None
        self.client.rpc_arguments.append((self.function_name, self.params))
        if self.client.accountability_items_error:
            raise RuntimeError("internal accountability database detail")
        if self.client.invalid_accountability_items_result:
            return SimpleNamespace(data=[{"id": "malformed"}])
        if not self.client.meeting_access:
            return SimpleNamespace(data=[])
        requested_status = self.params["p_status"]
        requested_review_state = self.params["p_review_state"]
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
            history = [
                entry
                for entry in self.client.action_item_history
                if entry["action_item_id"] == item.get("id")
            ]
            item_signals = fake_accountability_signals(item, history)
            review_record = self.client.action_item_signal_reviews.get(
                item["id"]
            )
            review_state = fake_signal_review_state(
                history,
                review_record,
                item_signals,
            )
            if requested_status == "all":
                matches = True
            elif requested_status == "overdue":
                matches = overdue
            elif requested_status == "needs_attention":
                matches = item["status"] != "completed"
            elif requested_status == "follow_up":
                matches = item["status"] != "completed"
            elif requested_status in {"open", "in_progress", "completed"}:
                matches = item["status"] == requested_status
            elif requested_status == "needs_review":
                matches = review_state["needs_review"]
            else:
                matches = requested_status in item_signals
            if requested_review_state == "reviewable":
                matches = matches and bool(item_signals)
            elif requested_review_state == "reviewed":
                matches = (
                    matches
                    and bool(item_signals)
                    and review_state["reviewed_at"] is not None
                    and not review_state["needs_review"]
                )
            elif requested_review_state == "needs_review":
                matches = matches and review_state["needs_review"]
            elif requested_review_state == "reopened_since_review":
                matches = (
                    matches
                    and bool(item_signals)
                    and review_state["reviewed_at"] is not None
                    and review_state["needs_review"]
                )
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
                        "accountability_signals": item_signals,
                        "reviewed_at": review_state["reviewed_at"],
                        "needs_review": review_state["needs_review"],
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
    def __init__(
        self,
        *,
        meeting_access: bool = True,
        invalid_token: bool = False,
    ) -> None:
        self.meeting_access = meeting_access
        self.invalid_token = invalid_token
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
        self.action_item_history: list[dict] = []
        self.action_item_signal_reviews: dict[str, dict] = {}
        self.invalid_signal_result = False
        self.invalid_review_result = False
        self.accountability_items_error = False
        self.invalid_accountability_items_result = False
        self.review_analytics_data: list[dict] | None = None
        self.review_analytics_error = False
        self.rpc_calls: list[str] = []
        self.rpc_arguments: list[tuple[str, dict]] = []
        self.verified_tokens: list[str] = []

        def get_user(token: str) -> SimpleNamespace:
            self.verified_tokens.append(token)
            if self.invalid_token:
                error = RuntimeError("Invalid token")
                error.status = 401
                raise error
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


def test_update_schema_accepts_partial_fields_and_supported_statuses() -> None:
    for status in ("open", "in_progress", "completed"):
        update = ActionItemUpdate(status=status)
        assert update.model_dump(exclude_unset=True) == {"status": status}

    with pytest.raises(ValidationError):
        ActionItemUpdate(status="blocked")
    with pytest.raises(ValidationError):
        ActionItemUpdate(status=None)
    with pytest.raises(ValidationError):
        ActionItemUpdate()


def test_update_schema_clears_blank_text_and_preserves_valid_text() -> None:
    update = ActionItemUpdate(
        owner="  Sam Lee ",
        due_date="   ",
        priority=None,
    )

    assert update.model_dump(exclude_unset=True) == {
        "owner": "Sam Lee",
        "due_date": None,
        "priority": None,
    }

    with pytest.raises(ValidationError):
        ActionItemUpdate(owner="x" * 201)


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
    assert supabase.rpc_arguments[-1] == (
        "get_my_action_item_accountability_summary",
        {},
    )


def test_review_analytics_counts_watermark_state_and_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    reviewed_id = "00000000-0000-0000-0000-000000000011"
    pending_id = "00000000-0000-0000-0000-000000000012"
    updated_since_review_id = "00000000-0000-0000-0000-000000000013"
    supabase = FakeSupabase()
    supabase.action_items = [
        {
            "id": item_id,
            "meeting_id": MEETING_ID,
            "meeting_title": "Planning",
            "text": text,
            "owner": None,
            "due_date": None,
            "priority": None,
            "status": "open",
            "created_at": now.isoformat(),
        }
        for item_id, text in (
            (reviewed_id, "Reviewed item"),
            (pending_id, "Pending item"),
            (updated_since_review_id, "Updated after review"),
        )
    ]
    supabase.action_item_history = [
        {
            "id": f"00000000-0000-0000-0001-{index:012d}",
            "action_item_id": action_item_id,
            "meeting_id": MEETING_ID,
            "action_item_text": text,
            "field_changed": "owner",
            "previous_value": None,
            "new_value": "Sam",
            "changed_at": changed_at.isoformat(),
        }
        for index, action_item_id, text, changed_at in (
            (1, reviewed_id, "Reviewed item", now - timedelta(seconds=3)),
            (2, pending_id, "Pending item", now - timedelta(seconds=2)),
            (
                3,
                updated_since_review_id,
                "Updated after review",
                now - timedelta(seconds=2),
            ),
            (
                4,
                updated_since_review_id,
                "Updated after review",
                now - timedelta(seconds=1),
            ),
        )
    ]
    supabase.action_item_history.append(
        {
            "id": "00000000-0000-0000-0001-000000000005",
            "action_item_id": updated_since_review_id,
            "meeting_id": MEETING_ID,
            "action_item_text": "Updated after review",
            "field_changed": "status",
            "previous_value": "completed",
            "new_value": "open",
            "changed_at": (now - timedelta(seconds=2)).isoformat(),
        }
    )
    supabase.action_item_signal_reviews[reviewed_id] = {
        "reviewed_at": now.isoformat(),
        "reviewed_through": (now - timedelta(seconds=3)).isoformat(),
    }
    supabase.action_item_signal_reviews[updated_since_review_id] = {
        "reviewed_at": (now - timedelta(seconds=2)).isoformat(),
        "reviewed_through": (now - timedelta(seconds=2)).isoformat(),
    }
    client = make_client(monkeypatch, supabase)

    response = client.get(
        "/api/meetings/action-items/review-analytics",
        headers={"Authorization": "Bearer phase9i-test"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "total_reviewable": 3,
        "reviewed": 1,
        "needs_review": 2,
        "reopened_since_review": 1,
        "review_coverage_percent": 33.3,
    }
    assert supabase.rpc_calls == ["get_my_action_item_review_analytics"]
    assert supabase.rpc_arguments[-1] == (
        "get_my_action_item_review_analytics",
        {},
    )
    assert ActionItemReviewAnalytics.model_validate(response.json())


def test_review_analytics_requires_authentication_and_handles_zero_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase = FakeSupabase()
    client = make_client(monkeypatch, supabase)

    unauthenticated = client.get(
        "/api/meetings/action-items/review-analytics",
    )
    response = client.get(
        "/api/meetings/action-items/review-analytics",
        headers={"Authorization": "Bearer phase9i-test"},
    )

    assert unauthenticated.status_code == 401
    assert response.status_code == 200
    assert response.json() == {
        "total_reviewable": 0,
        "reviewed": 0,
        "needs_review": 0,
        "reopened_since_review": 0,
        "review_coverage_percent": 0.0,
    }


@pytest.mark.parametrize(
    "data",
    [
        [],
        [
            {
                "total_reviewable": 2,
                "reviewed": 1,
                "needs_review": 0,
                "reopened_since_review": 0,
                "review_coverage_percent": 50,
            }
        ],
        [
            {
                "total_reviewable": 1,
                "reviewed": 1,
                "needs_review": 0,
                "reopened_since_review": 0,
                "review_coverage_percent": 100.05,
            }
        ],
        [
            {
                "total_reviewable": 3,
                "reviewed": 1,
                "needs_review": 2,
                "reopened_since_review": 0,
                "review_coverage_percent": 33.35,
            }
        ],
        [
            {
                "total_reviewable": "1",
                "reviewed": 1,
                "needs_review": 0,
                "reopened_since_review": 0,
                "review_coverage_percent": 100,
            }
        ],
        [
            {
                "total_reviewable": 0,
                "reviewed": 0,
                "needs_review": 0,
                "reopened_since_review": 0,
                "review_coverage_percent": 0,
                "unexpected": True,
            }
        ],
    ],
)
def test_review_analytics_rejects_malformed_rpc_data(
    monkeypatch: pytest.MonkeyPatch,
    data: list[dict],
) -> None:
    supabase = FakeSupabase()
    supabase.review_analytics_data = data
    client = make_client(monkeypatch, supabase)

    response = client.get(
        "/api/meetings/action-items/review-analytics",
        headers={"Authorization": "Bearer phase9i-test"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Unable to load action-item review analytics."
    )
    assert "unexpected" not in response.text


def test_review_analytics_hides_rpc_failures_and_validates_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failing_supabase = FakeSupabase()
    failing_supabase.review_analytics_error = True
    client = make_client(monkeypatch, failing_supabase)

    response = client.get(
        "/api/meetings/action-items/review-analytics",
        headers={"Authorization": "Bearer phase9i-test"},
    )
    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Unable to load action-item review analytics."
    )
    assert "internal analytics database detail" not in response.text

    with pytest.raises(ValidationError):
        ActionItemReviewAnalytics.model_validate(
            {
                "total_reviewable": 1,
                "reviewed": 1,
                "needs_review": 0,
                "reopened_since_review": 1,
                "review_coverage_percent": 100,
            }
        )


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
        for function_name, _ in supabase.rpc_arguments[:-1]
    )
    assert supabase.rpc_arguments[-1] == (
        "get_my_action_item_accountability_summary",
        {},
    )
    assert supabase.verified_tokens == ["test-token"] * (
        len(expected) + 1
    )
    assert all(
        set(parameters) == {"p_status", "p_offset", "p_review_state"}
        for _, parameters in supabase.rpc_arguments[:-1]
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
            {
                "p_status": "follow_up",
                "p_offset": 0,
                "p_review_state": "all",
            },
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
    TrackedActionItem.model_validate(response.json())
    assert supabase.action_item_updates == [{"status": "in_progress"}]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("owner", "Taylor"),
        ("due_date", "2026-10-30"),
        ("priority", "urgent"),
    ],
)
def test_action_item_patch_updates_metadata_without_changing_omitted_fields(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    supabase = FakeSupabase()
    sync_generated_action_items(
        supabase,
        MEETING_ID,
        [ActionItem(text="Send the draft", owner="Sam", due_date="Friday", priority="low")],
    )
    client = make_client(monkeypatch, supabase)

    response = client.patch(
        f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}",
        headers={"Authorization": "Bearer test-token"},
        json={field: value},
    )

    assert response.status_code == 200, response.text
    updated = TrackedActionItem.model_validate(response.json())
    assert getattr(updated, field) == value
    for omitted_field, original_value in (
        ("owner", "Sam"),
        ("due_date", "Friday"),
        ("priority", "low"),
        ("status", "open"),
    ):
        if omitted_field != field:
            assert getattr(updated, omitted_field) == original_value
    assert supabase.action_item_updates == [{field: value}]


def test_action_item_patch_supports_combined_updates_and_null_clears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase = FakeSupabase()
    sync_generated_action_items(
        supabase,
        MEETING_ID,
        [ActionItem(text="Send the draft", owner="Sam", due_date="Friday", priority="low")],
    )
    client = make_client(monkeypatch, supabase)
    item_url = f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}"
    headers = {"Authorization": "Bearer test-token"}

    combined = client.patch(
        item_url,
        headers=headers,
        json={
            "status": "in_progress",
            "owner": "Taylor",
            "due_date": "2026-11-02",
            "priority": "high",
        },
    )
    cleared = client.patch(
        item_url,
        headers=headers,
        json={"owner": None, "due_date": None, "priority": None},
    )

    assert combined.status_code == 200, combined.text
    assert TrackedActionItem.model_validate(combined.json()).model_dump(
        mode="json"
    )["status"] == "in_progress"
    assert cleared.status_code == 200, cleared.text
    cleared_item = TrackedActionItem.model_validate(cleared.json())
    assert (cleared_item.owner, cleared_item.due_date, cleared_item.priority) == (
        None,
        None,
        None,
    )
    assert supabase.action_item_updates == [
        {
            "status": "in_progress",
            "owner": "Taylor",
            "due_date": "2026-11-02",
            "priority": "high",
        },
        {"owner": None, "due_date": None, "priority": None},
    ]


def test_action_item_patch_rejects_empty_and_invalid_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase = FakeSupabase()
    sync_generated_action_items(
        supabase,
        MEETING_ID,
        [ActionItem(text="Send the draft")],
    )
    client = make_client(monkeypatch, supabase)
    item_url = f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}"
    headers = {"Authorization": "Bearer test-token"}

    empty = client.patch(item_url, headers=headers, json={})
    invalid_status = client.patch(
        item_url,
        headers=headers,
        json={"status": "blocked"},
    )
    null_status = client.patch(item_url, headers=headers, json={"status": None})
    client_overdue = client.patch(
        item_url,
        headers=headers,
        json={"is_overdue": True},
    )

    assert empty.status_code == 422
    assert invalid_status.status_code == 422
    assert null_status.status_code == 422
    assert client_overdue.status_code == 422
    assert supabase.action_item_updates == []


def test_action_item_patch_cannot_modify_another_meetings_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase = FakeSupabase()
    other_meeting_item = {
        "id": ACTION_ITEM_ID,
        "meeting_id": "00000000-0000-0000-0000-000000000003",
        "identity_key": "a" * 64,
        "text": "Other meeting task",
        "owner": "Sam",
        "due_date": None,
        "priority": None,
        "evidence": None,
        "status": "open",
        "created_at": "2026-10-25T00:00:00Z",
        "updated_at": "2026-10-25T00:00:00Z",
    }
    supabase.action_items.append(other_meeting_item)
    client = make_client(monkeypatch, supabase)

    response = client.patch(
        f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}",
        headers={"Authorization": "Bearer test-token"},
        json={"owner": "Taylor"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Action item not found or inaccessible."
    assert other_meeting_item["owner"] == "Sam"
    assert supabase.action_item_updates == []


def test_action_item_patch_requires_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client(monkeypatch, FakeSupabase())

    response = client.patch(
        f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}",
        json={"owner": "Taylor"},
    )

    assert response.status_code == 401


def test_action_item_patch_recalculates_overdue_on_the_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    past_due_date = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    supabase = FakeSupabase()
    sync_generated_action_items(
        supabase,
        MEETING_ID,
        [ActionItem(text="Send the draft", due_date=past_due_date)],
    )
    client = make_client(monkeypatch, supabase)

    response = client.patch(
        f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}",
        headers={"Authorization": "Bearer test-token"},
        json={"owner": "Taylor"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["is_overdue"] is True
    assert supabase.action_item_updates == [{"owner": "Taylor"}]


def test_action_item_patch_creates_history_for_each_changed_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase = FakeSupabase()
    sync_generated_action_items(
        supabase,
        MEETING_ID,
        [ActionItem(text="Send the draft", owner="Sam", due_date="Friday", priority="low")],
    )
    client = make_client(monkeypatch, supabase)

    response = client.patch(
        f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}",
        headers={"Authorization": "Bearer test-token"},
        json={
            "status": "in_progress",
            "owner": "Taylor",
            "due_date": "2026-10-30",
            "priority": "high",
        },
    )

    assert response.status_code == 200, response.text
    assert [
        (record["field_changed"], record["previous_value"], record["new_value"])
        for record in supabase.action_item_history
    ] == [
        ("status", "open", "in_progress"),
        ("owner", "Sam", "Taylor"),
        ("due_date", "Friday", "2026-10-30"),
        ("priority", "low", "high"),
    ]


def test_action_item_patch_records_metadata_clearing_and_ignores_noop_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase = FakeSupabase()
    sync_generated_action_items(
        supabase,
        MEETING_ID,
        [ActionItem(text="Send the draft", owner="Sam", due_date="Friday", priority="low")],
    )
    client = make_client(monkeypatch, supabase)
    item_url = f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}"
    headers = {"Authorization": "Bearer test-token"}

    noop = client.patch(item_url, headers=headers, json={"owner": "Sam"})
    assert noop.status_code == 200
    assert supabase.action_item_history == []

    cleared = client.patch(item_url, headers=headers, json={"owner": None})

    assert cleared.status_code == 200
    assert supabase.action_item_history == [
        {
            "id": "00000000-0000-0000-0000-000000000010",
            "action_item_id": ACTION_ITEM_ID,
            "meeting_id": MEETING_ID,
            "action_item_text": "Send the draft",
            "field_changed": "owner",
            "previous_value": "Sam",
            "new_value": None,
            "changed_at": "2026-10-27T00:00:00+00:00",
        }
    ]


def test_action_item_history_returns_valid_records_newest_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase = FakeSupabase()
    sync_generated_action_items(
        supabase,
        MEETING_ID,
        [ActionItem(text="Send the draft", owner="Sam", due_date="Friday")],
    )
    client = make_client(monkeypatch, supabase)
    headers = {"Authorization": "Bearer test-token"}
    item_url = f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}"

    for update in (
        {"owner": "Taylor"},
        {"due_date": "2026-10-30"},
        {"status": "in_progress"},
    ):
        assert client.patch(item_url, headers=headers, json=update).status_code == 200

    response = client.get(
        f"{item_url}/history",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    history = response.json()["items"]
    assert [
        (record["field_changed"], record["previous_value"], record["new_value"])
        for record in history
    ] == [
        ("status", "open", "in_progress"),
        ("due_date", "Friday", "2026-10-30"),
        ("owner", "Sam", "Taylor"),
    ]
    assert all(record["action_item_text"] == "Send the draft" for record in history)
    assert all(record["meeting_id"] == MEETING_ID for record in history)
    assert all(record["action_item_id"] == ACTION_ITEM_ID for record in history)
    assert all(record["changed_at"] for record in history)
    assert response.json()["accountability_signals"][:2] == [
        "repeated_updates",
        "stale",
    ]


def test_action_item_history_requires_authentication_and_valid_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}/history"
    unauthenticated = make_client(monkeypatch, FakeSupabase()).get(url)
    expired_client = make_client(
        monkeypatch,
        FakeSupabase(invalid_token=True),
    )

    expired = expired_client.get(
        url,
        headers={"Authorization": "Bearer test-token"},
    )

    assert unauthenticated.status_code == 401
    assert expired.status_code == 401


def test_action_item_history_is_scoped_to_owned_meeting_and_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inaccessible_meeting = FakeSupabase(meeting_access=False)
    inaccessible_meeting.action_item_history.append(
        {
            "id": "00000000-0000-0000-0000-000000000010",
            "action_item_id": ACTION_ITEM_ID,
            "meeting_id": MEETING_ID,
            "action_item_text": "Private task",
            "field_changed": "owner",
            "previous_value": None,
            "new_value": "Sam",
            "changed_at": "2026-10-27T00:00:00+00:00",
        }
    )
    client = make_client(monkeypatch, inaccessible_meeting)
    url = f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}/history"

    inaccessible = client.get(
        url,
        headers={"Authorization": "Bearer test-token"},
    )

    assert inaccessible.status_code == 404
    assert inaccessible.json()["detail"] == "Meeting not found or inaccessible."

    owned_client = make_client(monkeypatch, FakeSupabase())
    missing_item = owned_client.get(
        url,
        headers={"Authorization": "Bearer test-token"},
    )
    assert missing_item.status_code == 404
    assert missing_item.json()["detail"] == "Action item not found or inaccessible."


def test_accountability_signal_filters_classify_history_deterministically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    unresolved_reopened_id = ACTION_ITEM_ID
    unresolved_stale_id = "00000000-0000-0000-0000-000000000003"
    completed_id = "00000000-0000-0000-0000-000000000004"
    supabase = FakeSupabase()
    supabase.action_items = [
        {
            "id": unresolved_reopened_id,
            "meeting_id": MEETING_ID,
            "meeting_title": "Planning",
            "text": "Reopened task",
            "owner": "Taylor",
            "due_date": None,
            "priority": None,
            "status": "in_progress",
            "created_at": "2026-10-25T00:00:00Z",
        },
        {
            "id": unresolved_stale_id,
            "meeting_id": MEETING_ID,
            "meeting_title": "Planning",
            "text": "Stale task",
            "owner": None,
            "due_date": None,
            "priority": None,
            "status": "open",
            "created_at": "2026-10-24T00:00:00Z",
        },
        {
            "id": completed_id,
            "meeting_id": MEETING_ID,
            "meeting_title": "Planning",
            "text": "Completed task",
            "owner": None,
            "due_date": None,
            "priority": None,
            "status": "completed",
            "created_at": "2026-10-23T00:00:00Z",
        },
    ]
    supabase.action_item_history = [
        {
            "id": "00000000-0000-0000-0000-000000000101",
            "action_item_id": unresolved_reopened_id,
            "meeting_id": MEETING_ID,
            "action_item_text": "Reopened task",
            "field_changed": "status",
            "previous_value": "completed",
            "new_value": "open",
            "changed_at": now.isoformat(),
        },
        {
            "id": "00000000-0000-0000-0000-000000000102",
            "action_item_id": unresolved_reopened_id,
            "meeting_id": MEETING_ID,
            "action_item_text": "Reopened task",
            "field_changed": "owner",
            "previous_value": None,
            "new_value": "Taylor",
            "changed_at": now.isoformat(),
        },
        {
            "id": "00000000-0000-0000-0000-000000000103",
            "action_item_id": unresolved_stale_id,
            "meeting_id": MEETING_ID,
            "action_item_text": "Stale task",
            "field_changed": "priority",
            "previous_value": None,
            "new_value": "high",
            "changed_at": (now - timedelta(days=8)).isoformat(),
        },
        {
            "id": "00000000-0000-0000-0000-000000000104",
            "action_item_id": completed_id,
            "meeting_id": MEETING_ID,
            "action_item_text": "Completed task",
            "field_changed": "status",
            "previous_value": "open",
            "new_value": "completed",
            "changed_at": now.isoformat(),
        },
    ]
    client = make_client(monkeypatch, supabase)
    headers = {"Authorization": "Bearer test-token"}

    responses = {
        signal: client.get(
            "/api/meetings/action-items/accountability-items",
            params={"status": signal},
            headers=headers,
        )
        for signal in (
            "reopened",
            "repeated_updates",
            "stale",
            "recent_activity",
        )
    }

    assert all(response.status_code == 200 for response in responses.values())
    reopened = responses["reopened"].json()["items"]
    repeated = responses["repeated_updates"].json()["items"]
    stale = responses["stale"].json()["items"]
    recent = responses["recent_activity"].json()["items"]
    assert [item["text"] for item in reopened] == ["Reopened task"]
    assert [item["text"] for item in repeated] == ["Reopened task"]
    assert [item["text"] for item in stale] == [
        "Stale task",
        "Reopened task",
    ]
    assert [item["text"] for item in recent] == [
        "Reopened task",
        "Completed task",
    ]


def test_accountability_signals_are_included_and_completed_items_not_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    supabase = FakeSupabase()
    supabase.action_items = [
        {
            "id": ACTION_ITEM_ID,
            "meeting_id": MEETING_ID,
            "meeting_title": "Planning",
            "text": "Completed task",
            "owner": None,
            "due_date": None,
            "priority": None,
            "status": "completed",
            "created_at": now.isoformat(),
        }
    ]
    supabase.action_item_history = [
        {
            "id": "00000000-0000-0000-0000-000000000101",
            "action_item_id": ACTION_ITEM_ID,
            "meeting_id": MEETING_ID,
            "action_item_text": "Completed task",
            "field_changed": "status",
            "previous_value": "open",
            "new_value": "completed",
            "changed_at": now.isoformat(),
        }
    ]
    client = make_client(monkeypatch, supabase)

    response = client.get(
        "/api/meetings/action-items/accountability-items?status=all",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["accountability_signals"] == ["recent_activity"]
    assert supabase.rpc_arguments == [
        (
            "get_my_action_item_accountability_items",
            {"p_status": "all", "p_offset": 0, "p_review_state": "all"},
        )
    ]
    assert "user_id" not in supabase.rpc_arguments[0][1]
    assert ActionItemAccountabilityRecord.model_validate(item)


def test_accountability_signal_filters_validate_and_paginate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase = FakeSupabase()
    created_at = datetime.now(timezone.utc).isoformat()
    for index in range(1, 28):
        item_id = f"00000000-0000-0000-0000-{index:012d}"
        supabase.action_items.append(
            {
                "id": item_id,
                "meeting_id": MEETING_ID,
                "meeting_title": "Planning",
                "text": f"Recently updated {index}",
                "owner": None,
                "due_date": None,
                "priority": None,
                "status": "open",
                "created_at": created_at,
            }
        )
        supabase.action_item_history.append(
            {
                "id": f"00000000-0000-0000-0001-{index:012d}",
                "action_item_id": item_id,
                "meeting_id": MEETING_ID,
                "action_item_text": f"Recently updated {index}",
                "field_changed": "owner",
                "previous_value": None,
                "new_value": "Sam",
                "changed_at": created_at,
            }
        )
    client = make_client(monkeypatch, supabase)

    invalid = client.get(
        "/api/meetings/action-items/accountability-items?status=unknown_signal",
        headers={"Authorization": "Bearer test-token"},
    )
    first_page = client.get(
        "/api/meetings/action-items/accountability-items",
        params={"status": "recent_activity", "page": 1},
        headers={"Authorization": "Bearer test-token"},
    )
    second_page = client.get(
        "/api/meetings/action-items/accountability-items",
        params={"status": "recent_activity", "page": 2},
        headers={"Authorization": "Bearer test-token"},
    )

    assert invalid.status_code == 422
    assert first_page.status_code == second_page.status_code == 200
    assert len(first_page.json()["items"]) == 25
    assert first_page.json()["has_more"] is True
    assert len(second_page.json()["items"]) == 2
    assert second_page.json()["has_more"] is False
    assert second_page.json()["page"] == 2
    assert supabase.rpc_arguments[-2:] == [
        (
            "get_my_action_item_accountability_items",
            {
                "p_status": "recent_activity",
                "p_offset": 0,
                "p_review_state": "all",
            },
        ),
        (
            "get_my_action_item_accountability_items",
            {
                "p_status": "recent_activity",
                "p_offset": 25,
                "p_review_state": "all",
            },
        ),
    ]


def test_history_response_includes_validated_accountability_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase = FakeSupabase()
    sync_generated_action_items(
        supabase,
        MEETING_ID,
        [ActionItem(text="Send the draft")],
    )
    supabase.invalid_signal_result = True
    client = make_client(monkeypatch, supabase)

    response = client.get(
        f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}/history",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Unable to load action-item accountability signals."
    )


def test_action_item_signal_review_requires_authentication_and_owned_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = {"Authorization": "Bearer phase9h-test"}
    unauthenticated_client = make_client(monkeypatch, FakeSupabase())
    assert unauthenticated_client.post(
        f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}/review"
    ).status_code == 401

    invalid_token_client = make_client(
        monkeypatch,
        FakeSupabase(invalid_token=True),
    )
    assert invalid_token_client.post(
        f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}/review",
        headers=headers,
    ).status_code == 401

    inaccessible_client = make_client(
        monkeypatch,
        FakeSupabase(meeting_access=False),
    )
    assert inaccessible_client.post(
        f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}/review",
        headers=headers,
    ).status_code == 404

    missing_item_client = make_client(monkeypatch, FakeSupabase())
    assert missing_item_client.post(
        f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}/review",
        headers=headers,
    ).status_code == 404


def test_action_item_signal_review_marks_history_and_new_activity_resurfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    supabase = FakeSupabase()
    supabase.action_items = [
        {
            "id": ACTION_ITEM_ID,
            "meeting_id": MEETING_ID,
            "meeting_title": "Planning",
            "text": "Send the draft",
            "owner": None,
            "due_date": None,
            "priority": None,
            "status": "open",
            "created_at": now.isoformat(),
        }
    ]
    supabase.action_item_history = [
        {
            "id": "00000000-0000-0000-0000-000000000101",
            "action_item_id": ACTION_ITEM_ID,
            "meeting_id": MEETING_ID,
            "action_item_text": "Send the draft",
            "field_changed": "owner",
            "previous_value": None,
            "new_value": "Sam",
            "changed_at": now.isoformat(),
        }
    ]
    client = make_client(monkeypatch, supabase)
    headers = {"Authorization": "Bearer phase9h-test"}

    reviewed = client.post(
        f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}/review",
        headers=headers,
    )

    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["needs_review"] is False
    assert reviewed.json()["reviewed_at"]
    assert supabase.rpc_arguments[-1] == (
        "review_my_action_item_signals",
        {
            "p_meeting_id": MEETING_ID,
            "p_action_item_id": ACTION_ITEM_ID,
        },
    )
    assert "user_id" not in supabase.rpc_arguments[-1][1]

    history_response = client.get(
        f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}/history",
        headers=headers,
    )
    assert history_response.status_code == 200
    assert history_response.json()["needs_review"] is False
    assert history_response.json()["reviewed_at"] == reviewed.json()["reviewed_at"]
    assert supabase.rpc_arguments[-2:] == [
        (
            "get_my_action_item_accountability_signals",
            {"p_action_item_id": ACTION_ITEM_ID},
        ),
        (
            "get_my_action_item_signal_review_state",
            {"p_action_item_id": ACTION_ITEM_ID},
        ),
    ]

    reviewed_queue = client.get(
        "/api/meetings/action-items/accountability-items",
        params={"status": "needs_review", "review_state": "needs_review"},
        headers=headers,
    )
    assert reviewed_queue.status_code == 200
    assert reviewed_queue.json()["items"] == []
    acknowledged_queue = client.get(
        "/api/meetings/action-items/accountability-items",
        params={"review_state": "reviewed"},
        headers=headers,
    )
    assert acknowledged_queue.status_code == 200
    assert acknowledged_queue.json()["items"][0]["id"] == ACTION_ITEM_ID
    assert acknowledged_queue.json()["items"][0]["needs_review"] is False

    supabase.action_item_history.append(
        {
            "id": "00000000-0000-0000-0000-000000000102",
            "action_item_id": ACTION_ITEM_ID,
            "meeting_id": MEETING_ID,
            "action_item_text": "Send the draft",
            "field_changed": "priority",
            "previous_value": None,
            "new_value": "high",
            "changed_at": (now + timedelta(seconds=1)).isoformat(),
        }
    )
    reopened_queue = client.get(
        "/api/meetings/action-items/accountability-items",
        params={
            "status": "needs_review",
            "review_state": "reopened_since_review",
        },
        headers=headers,
    )
    assert reopened_queue.status_code == 200
    item = reopened_queue.json()["items"][0]
    assert item["id"] == ACTION_ITEM_ID
    assert item["needs_review"] is True
    assert item["reviewed_at"] == reviewed.json()["reviewed_at"]


def test_action_item_signal_review_rejects_empty_and_invalid_rpc_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase = FakeSupabase()
    sync_generated_action_items(
        supabase,
        MEETING_ID,
        [ActionItem(text="Send the draft")],
    )
    client = make_client(monkeypatch, supabase)
    headers = {"Authorization": "Bearer phase9h-test"}
    url = f"/api/meetings/{MEETING_ID}/action-items/{ACTION_ITEM_ID}/review"

    no_signals = client.post(url, headers=headers)
    assert no_signals.status_code == 422

    supabase.action_item_history.append(
        {
            "id": "00000000-0000-0000-0000-000000000101",
            "action_item_id": ACTION_ITEM_ID,
            "meeting_id": MEETING_ID,
            "action_item_text": "Send the draft",
            "field_changed": "owner",
            "previous_value": None,
            "new_value": "Sam",
            "changed_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    supabase.invalid_review_result = True
    invalid_result = client.post(url, headers=headers)
    assert invalid_result.status_code == 500
    assert invalid_result.json()["detail"] == (
        "Unable to mark action-item signals as reviewed."
    )


def test_needs_review_filter_validates_rpc_arguments_and_paginates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase = FakeSupabase()
    created_at = datetime.now(timezone.utc).isoformat()
    for index in range(1, 28):
        item_id = f"00000000-0000-0000-0000-{index:012d}"
        supabase.action_items.append(
            {
                "id": item_id,
                "meeting_id": MEETING_ID,
                "meeting_title": "Planning",
                "text": f"Review item {index}",
                "owner": None,
                "due_date": None,
                "priority": None,
                "status": "open",
                "created_at": created_at,
            }
        )
        supabase.action_item_history.append(
            {
                "id": f"00000000-0000-0000-0001-{index:012d}",
                "action_item_id": item_id,
                "meeting_id": MEETING_ID,
                "action_item_text": f"Review item {index}",
                "field_changed": "owner",
                "previous_value": None,
                "new_value": "Sam",
                "changed_at": created_at,
            }
        )
    client = make_client(monkeypatch, supabase)
    headers = {"Authorization": "Bearer phase9h-test"}

    invalid = client.get(
        "/api/meetings/action-items/accountability-items?status=reviewed",
        headers=headers,
    )
    first_page = client.get(
        "/api/meetings/action-items/accountability-items",
        params={"status": "all", "review_state": "needs_review", "page": 1},
        headers=headers,
    )
    second_page = client.get(
        "/api/meetings/action-items/accountability-items",
        params={"status": "all", "review_state": "needs_review", "page": 2},
        headers=headers,
    )

    assert invalid.status_code == 422
    assert first_page.status_code == second_page.status_code == 200
    assert len(first_page.json()["items"]) == 25
    assert first_page.json()["has_more"] is True
    assert len(second_page.json()["items"]) == 2
    assert all(item["needs_review"] for item in first_page.json()["items"])
    assert supabase.rpc_arguments[-2:] == [
        (
            "get_my_action_item_accountability_items",
            {
                "p_status": "all",
                "p_offset": 0,
                "p_review_state": "needs_review",
            },
        ),
        (
            "get_my_action_item_accountability_items",
            {
                "p_status": "all",
                "p_offset": 25,
                "p_review_state": "needs_review",
            },
        ),
    ]


def test_review_state_filters_are_database_rpc_arguments_and_compose_with_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    supabase = FakeSupabase()
    fixtures = [
        ("00000000-0000-0000-0000-000000000101", "completed", "reviewed"),
        ("00000000-0000-0000-0000-000000000102", "open", "needs_review"),
        ("00000000-0000-0000-0000-000000000103", "in_progress", "reopened"),
        ("00000000-0000-0000-0000-000000000104", "open", "not_reviewable"),
    ]
    for index, (item_id, status, review_mode) in enumerate(fixtures):
        changed_at = now - timedelta(minutes=10 - index)
        supabase.action_items.append(
            {
                "id": item_id,
                "meeting_id": MEETING_ID,
                "meeting_title": "Planning",
                "text": f"{review_mode} item",
                "owner": None,
                "due_date": None,
                "priority": None,
                "status": status,
                "created_at": changed_at.isoformat(),
            }
        )
        if review_mode == "not_reviewable":
            continue
        supabase.action_item_history.append(
            {
                "id": f"00000000-0000-0000-0001-{index + 101:012d}",
                "action_item_id": item_id,
                "meeting_id": MEETING_ID,
                "action_item_text": f"{review_mode} item",
                "field_changed": "owner",
                "previous_value": None,
                "new_value": "Sam",
                "changed_at": changed_at.isoformat(),
            }
        )
        if review_mode == "reviewed":
            reviewed_through = changed_at
            reviewed_at = now - timedelta(minutes=1)
        elif review_mode == "reopened":
            reviewed_through = changed_at - timedelta(minutes=1)
            reviewed_at = changed_at - timedelta(minutes=2)
        else:
            continue
        supabase.action_item_signal_reviews[item_id] = {
            "reviewed_through": reviewed_through.isoformat(),
            "reviewed_at": reviewed_at.isoformat(),
        }

    client = make_client(monkeypatch, supabase)
    headers = {"Authorization": "Bearer test-token"}
    default = client.get(
        "/api/meetings/action-items/accountability-items",
        headers=headers,
    )
    reviewable = client.get(
        "/api/meetings/action-items/accountability-items",
        params={"review_state": "reviewable"},
        headers=headers,
    )
    reviewed = client.get(
        "/api/meetings/action-items/accountability-items",
        params={"review_state": "reviewed"},
        headers=headers,
    )
    needs_review = client.get(
        "/api/meetings/action-items/accountability-items",
        params={"review_state": "needs_review"},
        headers=headers,
    )
    reopened = client.get(
        "/api/meetings/action-items/accountability-items",
        params={"review_state": "reopened_since_review"},
        headers=headers,
    )
    composed_reviewed = client.get(
        "/api/meetings/action-items/accountability-items",
        params={"status": "completed", "review_state": "reviewed"},
        headers=headers,
    )
    composed_needs_review = client.get(
        "/api/meetings/action-items/accountability-items",
        params={"status": "open", "review_state": "needs_review"},
        headers=headers,
    )
    invalid = client.get(
        "/api/meetings/action-items/accountability-items",
        params={"review_state": "unknown"},
        headers=headers,
    )

    assert default.status_code == 200
    assert len(default.json()["items"]) == 4
    assert len(reviewable.json()["items"]) == 3
    assert [item["text"] for item in reviewed.json()["items"]] == ["reviewed item"]
    assert [item["text"] for item in needs_review.json()["items"]] == [
        "needs_review item",
        "reopened item",
    ]
    assert [item["text"] for item in reopened.json()["items"]] == ["reopened item"]
    assert [item["text"] for item in composed_reviewed.json()["items"]] == [
        "reviewed item"
    ]
    assert [item["text"] for item in composed_needs_review.json()["items"]] == [
        "needs_review item"
    ]
    assert invalid.status_code == 422
    assert supabase.rpc_arguments[0][1] == {
        "p_status": "all",
        "p_offset": 0,
        "p_review_state": "all",
    }


def test_review_state_drilldown_requires_auth_and_scopes_database_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inaccessible = FakeSupabase(meeting_access=False)
    client = make_client(monkeypatch, inaccessible)
    no_auth = client.get(
        "/api/meetings/action-items/accountability-items",
        params={"review_state": "reviewed"},
    )
    inaccessible_result = client.get(
        "/api/meetings/action-items/accountability-items",
        params={"review_state": "reviewed"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert no_auth.status_code == 401
    assert inaccessible_result.status_code == 200
    assert inaccessible_result.json()["items"] == []
    assert inaccessible.rpc_arguments[-1][1]["p_review_state"] == "reviewed"


@pytest.mark.parametrize(
    "failure_field",
    ["accountability_items_error", "invalid_accountability_items_result"],
)
def test_review_state_drilldown_hides_rpc_failures_and_malformed_rows(
    monkeypatch: pytest.MonkeyPatch,
    failure_field: str,
) -> None:
    supabase = FakeSupabase()
    setattr(supabase, failure_field, True)
    client = make_client(monkeypatch, supabase)

    response = client.get(
        "/api/meetings/action-items/accountability-items",
        params={"review_state": "reopened_since_review"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Unable to load action-item accountability items."
    )
