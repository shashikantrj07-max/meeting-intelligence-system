import assert from "node:assert/strict";
import test from "node:test";

import {
  actionItemsResponseError,
  filterGeneratedActionItems,
  getActionItemHistoryFieldLabel,
  getActionItemHistoryState,
  getActionItemHistoryTimestamp,
  getActionItemHistoryValue,
  getMeetingActionItemAccountabilitySignalLabel,
  getActionItemReviewAnalyticsMetrics,
  getActionItemReviewAnalyticsState,
  findTrackedActionItem,
  isMeetingActionItemStatus,
  parseActionItemSignalReviewResponse,
  parseActionItemReviewAnalytics,
  parseActionItemHistoryResponse,
  parseGeneratedActionItems,
  parseTrackedActionItems,
} from "../src/lib/meeting-action-items-shared.ts";

test("parses review analytics and exposes all five readable metrics", () => {
  const analytics = parseActionItemReviewAnalytics({
    total_reviewable: 10,
    reviewed: 6,
    needs_review: 4,
    reopened_since_review: 2,
    review_coverage_percent: 60,
  });

  assert.deepEqual(
    getActionItemReviewAnalyticsMetrics(analytics).map(
      ({ label, value }) => [label, value],
    ),
    [
      ["Total reviewable", "10"],
      ["Reviewed", "6"],
      ["Needs review", "4"],
      ["Reopened since review", "2"],
      ["Review coverage", "60.0%"],
    ],
  );
  assert.match(
    getActionItemReviewAnalyticsMetrics(analytics)[2].description,
    /newer meaningful activity/,
  );
  assert.deepEqual(
    getActionItemReviewAnalyticsMetrics(analytics).map(({ key }) => key),
    [
      "total_reviewable",
      "reviewed",
      "needs_review",
      "reopened_since_review",
      "review_coverage_percent",
    ],
  );
});

test("handles zero-reviewable analytics and rejects malformed responses", () => {
  const zero = parseActionItemReviewAnalytics({
    total_reviewable: 0,
    reviewed: 0,
    needs_review: 0,
    reopened_since_review: 0,
    review_coverage_percent: 0,
  });
  assert.equal(
    getActionItemReviewAnalyticsMetrics(zero)[4].value,
    "0.0%",
  );
  assert.throws(
    () =>
      parseActionItemReviewAnalytics({
        ...zero,
        review_coverage_percent: 1,
      }),
    /invalid action-item review analytics/,
  );
  assert.throws(
    () =>
      parseActionItemReviewAnalytics({
        total_reviewable: 1,
        reviewed: 0,
        needs_review: 1,
        reopened_since_review: 2,
        review_coverage_percent: 0,
      }),
    /invalid action-item review analytics/,
  );
  assert.throws(
    () =>
      parseActionItemReviewAnalytics({
        total_reviewable: 0,
        reviewed: 0,
        needs_review: 0,
        reopened_since_review: 0,
        review_coverage_percent: 0,
        extra: true,
      }),
    /invalid action-item review analytics/,
  );
});

test("review analytics panel supports loading, error, empty, and loaded states", () => {
  const data = {
    total_reviewable: 1,
    reviewed: 1,
    needs_review: 0,
    reopened_since_review: 0,
    review_coverage_percent: 100,
  };
  assert.equal(getActionItemReviewAnalyticsState(true, null, null), "loading");
  assert.equal(
    getActionItemReviewAnalyticsState(false, "Network error", null),
    "error",
  );
  assert.equal(getActionItemReviewAnalyticsState(false, null, null), "empty");
  assert.equal(getActionItemReviewAnalyticsState(false, null, data), "loaded");
});

test("validates action-item history responses and renders readable changes", () => {
  const record = {
    id: "history-1",
    action_item_id: "action-1",
    meeting_id: "meeting-1",
    action_item_text: "Send the draft",
    field_changed: "owner",
    previous_value: null,
    new_value: "Sam",
    changed_at: "2026-10-27T12:00:00Z",
  };
  const response = {
    items: [record],
    accountability_signals: ["reopened", "recent_activity"],
    reviewed_at: null,
    needs_review: true,
  };

  assert.deepEqual(parseActionItemHistoryResponse(response), response);
  assert.throws(
    () =>
      parseActionItemHistoryResponse({
        ...response,
        items: [{ ...record, field_changed: "evidence" }],
      }),
    /invalid action-item history/,
  );
  assert.throws(
    () =>
      parseActionItemHistoryResponse({
        ...response,
        accountability_signals: ["generated_claim"],
      }),
    /invalid action-item history/,
  );
  assert.throws(
    () =>
      parseActionItemHistoryResponse({
        ...response,
        needs_review: "yes",
      }),
    /invalid action-item history/,
  );
  assert.equal(getActionItemHistoryFieldLabel("due_date"), "Due date");
  assert.equal(getActionItemHistoryValue(null), "Not set");
  assert.equal(getActionItemHistoryValue("  "), "Not set");
  assert.equal(getActionItemHistoryValue("Sam"), "Sam");
  assert.equal(
    getMeetingActionItemAccountabilitySignalLabel("repeated_updates"),
    "Repeated updates",
  );
  assert.notEqual(
    getActionItemHistoryTimestamp(record.changed_at),
    record.changed_at,
  );
  assert.equal(
    getActionItemHistoryTimestamp("not-a-date"),
    "not-a-date",
  );
});

test("validates server-confirmed action-item signal review responses", () => {
  const response = {
    reviewed_at: "2026-10-27T12:00:00Z",
    needs_review: false,
  };
  assert.deepEqual(parseActionItemSignalReviewResponse(response), response);
  assert.throws(
    () =>
      parseActionItemSignalReviewResponse({
        ...response,
        needs_review: true,
      }),
    /invalid action-item review/,
  );
  assert.throws(
    () =>
      parseActionItemSignalReviewResponse({
        ...response,
        reviewed_at: "not-a-date",
      }),
    /invalid action-item review/,
  );
});

test("identifies history loading, error, empty, and populated UI states", () => {
  const record = {
    id: "history-1",
    action_item_id: "action-1",
    meeting_id: "meeting-1",
    action_item_text: "Send the draft",
    field_changed: "status",
    previous_value: "open",
    new_value: "completed",
    changed_at: "2026-10-27T12:00:00Z",
  };

  assert.equal(getActionItemHistoryState(true, null, []), "loading");
  assert.equal(getActionItemHistoryState(false, "Network error", []), "error");
  assert.equal(getActionItemHistoryState(false, null, []), "empty");
  assert.equal(getActionItemHistoryState(false, null, [record]), "records");
});

test("parses structured action-item display data and tolerates missing fields", () => {
  assert.deepEqual(
    parseGeneratedActionItems([
      {
        text: "Send the draft",
        owner: "Sam",
        due_date: "Friday",
        priority: "high",
        evidence: "Sam will send the draft.",
      },
      { text: "Review the plan", owner: null },
      { text: "   " },
      null,
    ]),
    [
      {
        text: "Send the draft",
        owner: "Sam",
        due_date: "Friday",
        priority: "high",
        evidence: "Sam will send the draft.",
      },
      {
        text: "Review the plan",
        owner: null,
        due_date: null,
        priority: null,
        evidence: null,
      },
    ],
  );
});

test("matches persisted workflow records to regenerated items consistently", () => {
  const tracked = {
    id: "action-1",
    meeting_id: "meeting-1",
    identity_key: "key",
    text: "Send the draft",
    owner: "Sam",
    due_date: "Friday",
    priority: "high",
    evidence: null,
    status: "completed",
    is_overdue: false,
    created_at: "2026-10-25T00:00:00Z",
    updated_at: "2026-10-25T00:00:00Z",
  };

  assert.equal(findTrackedActionItem(" send   the DRAFT ", [tracked]), tracked);
  assert.equal(findTrackedActionItem("Review the plan", [tracked]), undefined);
});

test("recognizes only the supported action-item workflow statuses", () => {
  assert.equal(isMeetingActionItemStatus("open"), true);
  assert.equal(isMeetingActionItemStatus("in_progress"), true);
  assert.equal(isMeetingActionItemStatus("completed"), true);
  assert.equal(isMeetingActionItemStatus("blocked"), false);
});

test("validates action-item API data and surfaces recoverable server errors", () => {
  const record = {
    id: "action-1",
    meeting_id: "meeting-1",
    identity_key: "a".repeat(64),
    text: "Send the draft",
    owner: null,
    due_date: null,
    priority: null,
    evidence: null,
    status: "open",
    is_overdue: false,
    created_at: "2026-10-25T00:00:00Z",
    updated_at: "2026-10-25T00:00:00Z",
  };

  assert.deepEqual(parseTrackedActionItems({ items: [record] }), [record]);
  assert.throws(
    () => parseTrackedActionItems({ items: [{ ...record, status: "blocked" }] }),
    /invalid tracked action items/,
  );
  assert.equal(
    actionItemsResponseError(
      { detail: "Action item not found or inaccessible." },
      "Fallback",
    ),
    "Action item not found or inaccessible.",
  );
  assert.equal(actionItemsResponseError(null, "Fallback"), "Fallback");
});

test("filters generated items by persisted status and overdue flag", () => {
  const generated = parseGeneratedActionItems([
    { text: "Open overdue task" },
    { text: "In progress overdue task" },
    { text: "Completed task" },
    { text: "Not yet tracked" },
  ]);
  const tracked = [
    {
      id: "action-1",
      meeting_id: "meeting-1",
      identity_key: "a".repeat(64),
      text: "Open overdue task",
      owner: null,
      due_date: "2026-10-24",
      priority: null,
      evidence: null,
      status: "open",
      is_overdue: true,
      created_at: "2026-10-25T00:00:00Z",
      updated_at: "2026-10-25T00:00:00Z",
    },
    {
      id: "action-2",
      meeting_id: "meeting-1",
      identity_key: "b".repeat(64),
      text: "In progress overdue task",
      owner: null,
      due_date: "2026-10-24",
      priority: null,
      evidence: null,
      status: "in_progress",
      is_overdue: true,
      created_at: "2026-10-25T00:00:00Z",
      updated_at: "2026-10-25T00:00:00Z",
    },
    {
      id: "action-3",
      meeting_id: "meeting-1",
      identity_key: "c".repeat(64),
      text: "Completed task",
      owner: null,
      due_date: "2026-10-24",
      priority: null,
      evidence: null,
      status: "completed",
      is_overdue: false,
      created_at: "2026-10-25T00:00:00Z",
      updated_at: "2026-10-25T00:00:00Z",
    },
  ];

  assert.deepEqual(
    filterGeneratedActionItems(generated, tracked, "overdue").map(
      ({ generated: item }) => item.text,
    ),
    ["Open overdue task", "In progress overdue task"],
  );
  assert.deepEqual(
    filterGeneratedActionItems(generated, tracked, "completed").map(
      ({ generated: item }) => item.text,
    ),
    ["Completed task"],
  );
  assert.equal(filterGeneratedActionItems(generated, tracked, "all").length, 4);
});
