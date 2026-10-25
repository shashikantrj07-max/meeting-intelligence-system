import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from app.routers.meeting_insights import (
    _generate_and_save_insights as generate_manually,
)
from app.routers.meeting_transcription import (
    _generate_and_save_insights as generate_automatically,
)
from app.schemas.meeting_insights import MeetingInsights
from app.services.ai.gemini import _build_prompt, _gemini_response_schema


class GeminiResponseSchemaTests(unittest.TestCase):
    def test_response_schema_omits_unsupported_additional_properties(self) -> None:
        schema = _gemini_response_schema()

        def find_additional_properties(value: object) -> list[str]:
            found: list[str] = []
            if isinstance(value, dict):
                found.extend(
                    key
                    for key in value
                    if key in {"additionalProperties", "additional_properties"}
                )
                for nested_value in value.values():
                    found.extend(find_additional_properties(nested_value))
            elif isinstance(value, list):
                for nested_value in value:
                    found.extend(find_additional_properties(nested_value))
            return found

        self.assertEqual(find_additional_properties(schema), [])
        self.assertEqual(
            set(schema["properties"]),
            {
                "summary",
                "key_decisions",
                "action_items",
                "risks_blockers",
                "discussion_points",
                "open_questions",
                "next_steps",
            },
        )

    def test_prompt_requires_evidence_and_conservative_extraction(self) -> None:
        prompt = _build_prompt("The transcript text.")

        for instruction in (
            "copied directly from the transcript",
            "Never invent evidence",
            "set evidence to null",
            "actual decision or commitment",
            "suggestions, opinions, or historical statements",
            "concrete tasks or commitments",
            "do not infer an owner or deadline",
            "actual concern, obstacle, dependency, or potential problem",
            "ordinary technical discussion",
        ):
            with self.subTest(instruction=instruction):
                self.assertIn(instruction, prompt)

        self.assertTrue(prompt.endswith("Transcript:\nThe transcript text."))

    def test_meeting_insights_still_rejects_unexpected_fields(self) -> None:
        invalid_payloads = (
            {"summary": "A summary", "unexpected": True},
            {
                "summary": "A summary",
                "key_decisions": [{"text": "A decision", "unexpected": True}],
            },
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    MeetingInsights.model_validate_json(json.dumps(payload))

    def test_meeting_insights_validates_structured_categories_and_legacy_payloads(
        self,
    ) -> None:
        legacy = MeetingInsights.model_validate_json(
            json.dumps(
                {
                    "summary": "A legacy meeting summary.",
                    "key_decisions": [{"text": "Approve the proposal."}],
                    "action_items": [{"text": "Send the proposal.", "owner": "Alex"}],
                    "risks_blockers": [{"text": "The launch date is uncertain."}],
                }
            )
        )
        self.assertEqual(legacy.discussion_points, [])
        self.assertEqual(legacy.open_questions, [])
        self.assertEqual(legacy.next_steps, [])

        structured = MeetingInsights.model_validate_json(
            json.dumps(
                {
                    "summary": "A structured meeting summary.",
                    "key_decisions": [
                        {"text": "Approve the proposal.", "evidence": "Approved."}
                    ],
                    "action_items": [
                        {
                            "text": "Send the proposal.",
                            "owner": "Alex",
                            "due_date": "Friday",
                            "priority": "high",
                            "evidence": "Alex will send it Friday.",
                        }
                    ],
                    "risks_blockers": [
                        {"text": "The launch date is uncertain.", "evidence": "Date TBD."}
                    ],
                    "discussion_points": [
                        {"text": "Launch scope.", "evidence": "Scope was discussed."}
                    ],
                    "open_questions": [
                        {"text": "Which region first?", "evidence": "No decision yet."}
                    ],
                    "next_steps": [
                        {"text": "Confirm the region.", "evidence": "Confirm next week."}
                    ],
                }
            )
        )

        self.assertEqual(
            structured.model_dump(mode="json")["discussion_points"],
            [{"text": "Launch scope.", "evidence": "Scope was discussed."}],
        )
        self.assertEqual(
            structured.model_dump(mode="json")["open_questions"],
            [{"text": "Which region first?", "evidence": "No decision yet."}],
        )
        self.assertEqual(
            structured.model_dump(mode="json")["next_steps"],
            [{"text": "Confirm the region.", "evidence": "Confirm next week."}],
        )
        self.assertEqual(structured.action_items[0].priority, "high")

    def test_evidence_can_be_null_or_omitted(self) -> None:
        insights = MeetingInsights.model_validate(
            {
                "summary": "Summary.",
                "key_decisions": [{"text": "Decision.", "evidence": None}],
                "action_items": [{"text": "Task."}],
                "risks_blockers": [{"text": "Risk.", "evidence": None}],
                "discussion_points": [{"text": "Topic.", "evidence": None}],
                "open_questions": [{"text": "Question."}],
                "next_steps": [{"text": "Follow up.", "evidence": None}],
            }
        )

        self.assertIsNone(insights.key_decisions[0].evidence)
        self.assertIsNone(insights.action_items[0].evidence)
        self.assertIsNone(insights.risks_blockers[0].evidence)
        self.assertIsNone(insights.discussion_points[0].evidence)
        self.assertIsNone(insights.open_questions[0].evidence)
        self.assertIsNone(insights.next_steps[0].evidence)


class _FakeSupabaseQuery:
    def __init__(self, supabase: "_FakeSupabase", table: str) -> None:
        self.supabase = supabase
        self.table_name = table
        self.operation = "select"

    def select(self, *_args: object, **_kwargs: object) -> "_FakeSupabaseQuery":
        return self

    def eq(self, *_args: object, **_kwargs: object) -> "_FakeSupabaseQuery":
        return self

    def maybe_single(self) -> "_FakeSupabaseQuery":
        return self

    def single(self) -> "_FakeSupabaseQuery":
        return self

    def upsert(
        self,
        payload: dict[str, object] | list[dict[str, object]],
        *,
        on_conflict: str,
    ) -> "_FakeSupabaseQuery":
        self.operation = "upsert"
        self.supabase.upserts.append((self.table_name, payload, on_conflict))
        return self

    def update(self, _values: dict[str, object]) -> "_FakeSupabaseQuery":
        self.operation = "update"
        return self

    def execute(self) -> SimpleNamespace:
        if self.table_name == "meeting_insights" and self.operation == "upsert":
            return SimpleNamespace(data={"id": "insight-id"})
        if self.operation == "update":
            return SimpleNamespace(data=[{"meeting_id": "meeting-id"}])
        return SimpleNamespace(data={"meeting_id": "meeting-id"})


class _FakeSupabase:
    def __init__(self) -> None:
        self.upserts: list[
            tuple[
                str,
                dict[str, object] | list[dict[str, object]],
                str,
            ]
        ] = []

    def schema(self, _schema: str) -> "_FakeSupabase":
        return self

    def table(self, table: str) -> _FakeSupabaseQuery:
        return _FakeSupabaseQuery(self, table)


class InsightPersistenceTests(unittest.TestCase):
    def test_automatic_and_manual_paths_persist_the_same_structured_payload(
        self,
    ) -> None:
        insights = MeetingInsights.model_validate(
            {
                "summary": "Meeting summary.",
                "key_decisions": [
                    {"text": "Approved plan.", "evidence": "We approve the plan."}
                ],
                "action_items": [
                    {
                        "text": "Send the plan.",
                        "owner": "Morgan",
                        "due_date": "Friday",
                        "priority": "high",
                        "evidence": "Morgan will send the plan Friday.",
                    }
                ],
                "risks_blockers": [
                    {"text": "Vendor delay.", "evidence": "The vendor is behind."}
                ],
                "discussion_points": [
                    {"text": "Launch scope.", "evidence": "We discussed launch scope."}
                ],
                "open_questions": [
                    {"text": "Which market?", "evidence": "We have not chosen a market."}
                ],
                "next_steps": [
                    {"text": "Confirm the market.", "evidence": "Confirm this week."}
                ],
            }
        )
        expected_payload = {
            "meeting_id": "meeting-id",
            **insights.model_dump(mode="json"),
        }
        persisted_payloads: list[dict[str, object]] = []

        generation_paths = (
            (
                "app.routers.meeting_insights.GeminiMeetingInsightsProvider",
                generate_manually,
            ),
            (
                "app.routers.meeting_transcription.GeminiMeetingInsightsProvider",
                generate_automatically,
            ),
        )
        for provider_path, generate in generation_paths:
            supabase = _FakeSupabase()
            with patch(provider_path) as provider:
                provider.return_value.generate.return_value = insights
                generate(
                    supabase,
                    "meeting-id",
                    "Transcript.",
                    "2026-10-25T00:00:00Z",
                )

            insight_upserts = [
                entry for entry in supabase.upserts if entry[0] == "meeting_insights"
            ]
            action_item_upserts = [
                entry
                for entry in supabase.upserts
                if entry[0] == "meeting_action_items"
            ]
            self.assertEqual(len(insight_upserts), 1)
            self.assertEqual(len(action_item_upserts), 1)
            table, payload, conflict = insight_upserts[0]
            self.assertEqual(table, "meeting_insights")
            self.assertEqual(conflict, "meeting_id")
            self.assertEqual(payload, expected_payload)
            action_table, action_records, action_conflict = action_item_upserts[0]
            self.assertEqual(action_table, "meeting_action_items")
            self.assertEqual(action_conflict, "meeting_id,identity_key")
            self.assertEqual(len(action_records), 1)
            self.assertEqual(action_records[0]["text"], "Send the plan.")
            self.assertEqual(
                action_records[0]["evidence"],
                "Morgan will send the plan Friday.",
            )
            persisted_payloads.append(payload)

        self.assertEqual(persisted_payloads[0], persisted_payloads[1])
