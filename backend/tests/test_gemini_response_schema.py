import json
import unittest

from pydantic import ValidationError

from app.schemas.meeting_insights import MeetingInsights
from app.services.ai.gemini import _gemini_response_schema


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
