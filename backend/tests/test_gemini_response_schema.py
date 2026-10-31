import json
import re
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from google import genai
from google.genai import types
from pydantic import ValidationError

from app.routers.meeting_insights import (
    PROCESSING_STALE_AFTER,
    _generate_and_save_insights as generate_manually,
)
from app.routers.meeting_transcription import (
    _generate_and_save_insights as generate_automatically,
)
from app.schemas.meeting_insights import MeetingInsights
from app.services.ai.gemini import (
    GEMINI_REQUEST_TIMEOUT_MS,
    GEMINI_RETRY_ATTEMPTS,
    GEMINI_RETRY_HTTP_STATUS_CODES,
    GEMINI_RETRY_MAX_DELAY_SECONDS,
    GeminiMeetingInsightsProvider,
    _build_prompt,
    _gemini_response_schema,
)


_GENAI_CLIENT = genai.Client


class GeminiProviderRetryTests(unittest.TestCase):
    def _provider_for_responses(
        self,
        responses: list[tuple[int, dict[str, object]]],
    ) -> tuple[GeminiMeetingInsightsProvider, list[int], types.HttpOptions]:
        request_count = [0]
        configured_options: list[types.HttpOptions] = []

        def respond(request: httpx.Request) -> httpx.Response:
            del request
            response_index = request_count[0]
            request_count[0] += 1
            status, payload = responses[min(response_index, len(responses) - 1)]
            return httpx.Response(status, json=payload)

        def create_client(
            *,
            api_key: str,
            http_options: types.HttpOptions,
        ) -> genai.Client:
            configured_options.append(http_options)
            test_options = http_options.model_copy(
                update={
                    "httpx_client": httpx.Client(
                        transport=httpx.MockTransport(respond)
                    )
                }
            )
            return _GENAI_CLIENT(api_key=api_key, http_options=test_options)

        with patch(
            "app.services.ai.gemini.genai.Client",
            side_effect=create_client,
        ):
            provider = GeminiMeetingInsightsProvider(
                api_key="test-key",
                model="gemini-test",
            )

        self.addCleanup(provider.client.close)
        return provider, request_count, configured_options[0]

    @staticmethod
    def _success_payload() -> dict[str, object]:
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "summary": "Meeting summary.",
                                        "key_decisions": [],
                                        "action_items": [],
                                        "risks_blockers": [],
                                        "discussion_points": [],
                                        "open_questions": [],
                                        "next_steps": [],
                                    }
                                )
                            }
                        ],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }
            ]
        }

    @staticmethod
    def _api_error_payload(code: int, status: str) -> dict[str, object]:
        return {
            "error": {
                "code": code,
                "message": status,
                "status": status,
            }
        }

    def test_successful_request_uses_one_attempt_and_keeps_timeout(self) -> None:
        provider, request_count, http_options = self._provider_for_responses(
            [(200, self._success_payload())]
        )

        with self.assertLogs("app.services.ai.gemini", level="INFO") as logs:
            result = provider.generate("Transcript.")

        self.assertEqual(result.summary, "Meeting summary.")
        self.assertEqual(request_count[0], 1)
        self.assertTrue(
            any(
                "attempt 1/3 completed" in message
                and "final_outcome=success" in message
                for message in logs.output
            )
        )
        self.assertRegex(
            "\n".join(logs.output),
            r"request_id=[0-9a-f]{32}",
        )
        self.assertEqual(http_options.timeout, GEMINI_REQUEST_TIMEOUT_MS)
        retry_options = http_options.retry_options
        self.assertIsNotNone(retry_options)
        assert retry_options is not None
        self.assertEqual(
            retry_options.attempts,
            GEMINI_RETRY_ATTEMPTS,
        )
        self.assertEqual(
            retry_options.http_status_codes,
            list(GEMINI_RETRY_HTTP_STATUS_CODES),
        )
        self.assertEqual(retry_options.initial_delay, 1.0)
        self.assertEqual(
            retry_options.max_delay,
            GEMINI_RETRY_MAX_DELAY_SECONDS,
        )
        self.assertEqual(retry_options.exp_base, 2.0)
        self.assertEqual(retry_options.jitter, 1.0)

    def test_transient_504_retries_then_succeeds(self) -> None:
        provider, request_count, _ = self._provider_for_responses(
            [
                (504, self._api_error_payload(504, "DEADLINE_EXCEEDED")),
                (200, self._success_payload()),
            ]
        )

        with self.assertLogs("google_genai._api_client", level="INFO") as logs:
            with self.assertLogs(
                "app.services.ai.gemini",
                level="INFO",
            ) as provider_logs:
                result = provider.generate("Transcript.")

        self.assertEqual(result.summary, "Meeting summary.")
        self.assertEqual(request_count[0], 2)
        self.assertTrue(
            any(
                "attempt 1/3 failed" in message
                and "status=504" in message
                and "will_retry=true" in message
                and "retry_delay_seconds=" in message
                and "elapsed_total_ms=" in message
                and " elapsed_ms=" not in message
                for message in logs.output
            )
        )
        retry_message = next(
            message for message in logs.output if "will_retry=true" in message
        )
        self.assertRegex(
            retry_message,
            r"retry_delay_seconds=\d+(?:\.\d+)?",
        )
        self.assertFalse(any("DEADLINE_EXCEEDED" in message for message in logs.output))
        self.assertFalse(any("Deadline expired" in message for message in logs.output))
        correlated_messages = "\n".join(logs.output + provider_logs.output)
        request_ids = set(
            re.findall(r"request_id=([0-9a-f]{32})", correlated_messages)
        )
        self.assertEqual(len(request_ids), 1)
        self.assertIn("attempt 2/3 completed", correlated_messages)

    def test_retry_exhaustion_propagates_provider_error(self) -> None:
        provider, request_count, _ = self._provider_for_responses(
            [(504, self._api_error_payload(504, "DEADLINE_EXCEEDED"))]
        )

        with self.assertLogs("google_genai._api_client", level="INFO") as sdk_logs:
            with (
                self.assertRaisesRegex(
                    RuntimeError,
                    "Gemini API request failed",
                ) as raised,
                self.assertLogs("app.services.ai.gemini", level="ERROR") as logs,
            ):
                provider.generate("Transcript.")

        self.assertEqual(request_count[0], GEMINI_RETRY_ATTEMPTS)
        self.assertIn("status=504", str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)
        self.assertTrue(
            any(
                "attempt 3/3 failed" in message
                and "status=504" in message
                and "will_retry=false" in message
                and "final_outcome=failure" in message
                and "elapsed_total_ms=" in message
                and " elapsed_ms=" not in message
                for message in logs.output
            )
        )
        retry_logs = [
            message for message in sdk_logs.output if "will_retry=true" in message
        ]
        self.assertEqual(len(retry_logs), GEMINI_RETRY_ATTEMPTS - 1)
        self.assertTrue(
            all(
                f"attempt {index}/3 failed" in message and "status=504" in message
                for index, message in enumerate(retry_logs, start=1)
            )
        )
        self.assertTrue(
            all(
                re.search(r"retry_delay_seconds=\d+(?:\.\d+)?", message)
                for message in retry_logs
            )
        )
        self.assertFalse(any("DEADLINE_EXCEEDED" in message for message in sdk_logs.output))
        self.assertFalse(any("Deadline expired" in message for message in sdk_logs.output))
        self.assertFalse(any("DEADLINE_EXCEEDED" in message for message in logs.output))
        self.assertFalse(any("Deadline expired" in message for message in logs.output))
        correlated_messages = "\n".join(sdk_logs.output + logs.output)
        request_ids = set(
            re.findall(r"request_id=([0-9a-f]{32})", correlated_messages)
        )
        self.assertEqual(len(request_ids), 1)

    def test_permanent_client_error_is_not_retried(self) -> None:
        provider, request_count, http_options = self._provider_for_responses(
            [(400, self._api_error_payload(400, "INVALID_ARGUMENT"))]
        )

        with self.assertRaisesRegex(RuntimeError, "Gemini API request failed"):
            provider.generate("Transcript.")

        self.assertEqual(request_count[0], 1)
        retry_options = http_options.retry_options
        self.assertIsNotNone(retry_options)
        assert retry_options is not None
        self.assertNotIn(400, retry_options.http_status_codes)

    def test_client_initialization_logs_runtime_and_effective_options(self) -> None:
        with self.assertLogs("app.services.ai.gemini", level="INFO") as logs:
            provider, _, http_options = self._provider_for_responses(
                [(200, self._success_payload())]
            )

        self.assertIsNotNone(provider.client)
        messages = "\n".join(logs.output)
        self.assertIn("sdk_version=", messages)
        self.assertIn("python=", messages)
        self.assertIn(f"'timeout': {GEMINI_REQUEST_TIMEOUT_MS}", messages)
        self.assertIn(f"'attempts': {GEMINI_RETRY_ATTEMPTS}", messages)
        self.assertIn(
            f"'http_status_codes': {list(GEMINI_RETRY_HTTP_STATUS_CODES)}",
            messages,
        )
        retry_options = http_options.retry_options
        self.assertIsNotNone(retry_options)
        assert retry_options is not None
        self.assertEqual(
            retry_options.http_status_codes,
            list(GEMINI_RETRY_HTTP_STATUS_CODES),
        )

    def test_exhausted_retries_mark_processing_attempt_failed(self) -> None:
        provider, request_count, _ = self._provider_for_responses(
            [(504, self._api_error_payload(504, "DEADLINE_EXCEEDED"))]
        )
        supabase = _FakeSupabase()

        with patch(
            "app.routers.meeting_insights.GeminiMeetingInsightsProvider",
            return_value=provider,
        ):
            generate_manually(
                supabase,
                "meeting-id",
                "Transcript.",
                "2026-10-25T00:00:00Z",
            )

        failed_attempt_updates = [
            values
            for table, values in supabase.updates
            if table == "meeting_processing" and values.get("stage") == "failed"
        ]
        self.assertEqual(request_count[0], GEMINI_RETRY_ATTEMPTS)
        self.assertEqual(len(failed_attempt_updates), 1)
        self.assertEqual(supabase.upserts, [])
        worst_case_request_time = timedelta(
            seconds=(
                GEMINI_RETRY_ATTEMPTS * (GEMINI_REQUEST_TIMEOUT_MS / 1000)
                + (GEMINI_RETRY_ATTEMPTS - 1) * GEMINI_RETRY_MAX_DELAY_SECONDS
            )
        )
        self.assertGreater(PROCESSING_STALE_AFTER, worst_case_request_time)


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

    def update(self, values: dict[str, object]) -> "_FakeSupabaseQuery":
        self.operation = "update"
        self.supabase.updates.append((self.table_name, values))
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
        self.updates: list[tuple[str, dict[str, object]]] = []

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
