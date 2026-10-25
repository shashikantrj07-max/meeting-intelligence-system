import assert from "node:assert/strict";
import test from "node:test";

import {
  actionItemsResponseError,
  findTrackedActionItem,
  isMeetingActionItemStatus,
  parseGeneratedActionItems,
  parseTrackedActionItems,
} from "../src/lib/meeting-action-items-shared.ts";

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
