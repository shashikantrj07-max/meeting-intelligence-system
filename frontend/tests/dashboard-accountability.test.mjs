import assert from "node:assert/strict";
import test from "node:test";

import {
  buildActionItemAccountabilityHref,
  buildActionItemMeetingHref,
  buildDashboardFilterHref,
  getActionItemFollowUpReasonLabel,
  parseActionItemAccountabilityFilter,
  parseActionItemsPage,
} from "../src/lib/dashboard-accountability.ts";

const dashboardFilters = (search, status) => ({ search, status });

test("parses supported accountability filter values and ignores unknown values", () => {
  for (const filter of [
    "all",
    "open",
    "in_progress",
    "completed",
    "overdue",
    "needs_attention",
    "follow_up",
  ]) {
    assert.equal(parseActionItemAccountabilityFilter(filter), filter);
  }
  assert.equal(parseActionItemAccountabilityFilter("blocked"), null);
  assert.equal(parseActionItemAccountabilityFilter(["open", "completed"]), null);
  assert.equal(parseActionItemAccountabilityFilter(undefined), null);
});

test("parses page values safely and normalizes invalid values", () => {
  assert.equal(parseActionItemsPage("1"), 1);
  assert.equal(parseActionItemsPage("27"), 27);
  assert.equal(parseActionItemsPage("0"), 1);
  assert.equal(parseActionItemsPage("-1"), 1);
  assert.equal(parseActionItemsPage("invalid"), 1);
  assert.equal(parseActionItemsPage("100001"), 1);
  assert.equal(parseActionItemsPage(["2"]), 1);
});

test("accountability card links preserve dashboard search and status filters", () => {
  const filters = dashboardFilters("quarterly review", "completed");
  const href = buildActionItemAccountabilityHref(filters, "in_progress");
  const query = new URLSearchParams(href.split("?")[1]);

  assert.equal(href.startsWith("/dashboard?"), true);
  assert.equal(query.get("q"), "quarterly review");
  assert.equal(query.get("status"), "completed");
  assert.equal(query.get("actionItemStatus"), "in_progress");
  assert.equal(query.has("actionItemsPage"), false);
});

test("pagination links retain the selected filter and dashboard parameters", () => {
  const filters = dashboardFilters("planning", "failed");
  const href = buildActionItemAccountabilityHref(filters, "overdue", 2);
  const query = new URLSearchParams(href.split("?")[1]);

  assert.equal(query.get("q"), "planning");
  assert.equal(query.get("status"), "failed");
  assert.equal(query.get("actionItemStatus"), "overdue");
  assert.equal(query.get("actionItemsPage"), "2");
});

test("needs-attention links select the prioritized existing drill-down", () => {
  const filters = dashboardFilters("budget", "processing");
  const href = buildActionItemAccountabilityHref(
    filters,
    "needs_attention",
  );
  const query = new URLSearchParams(href.split("?")[1]);

  assert.equal(query.get("q"), "budget");
  assert.equal(query.get("status"), "processing");
  assert.equal(query.get("actionItemStatus"), "needs_attention");
});

test("follow-up links preserve dashboard filters and pagination", () => {
  const filters = dashboardFilters("quarterly review", "completed");
  const href = buildActionItemAccountabilityHref(filters, "follow_up", 3);
  const query = new URLSearchParams(href.split("?")[1]);

  assert.equal(query.get("q"), "quarterly review");
  assert.equal(query.get("status"), "completed");
  assert.equal(query.get("actionItemStatus"), "follow_up");
  assert.equal(query.get("actionItemsPage"), "3");
  assert.equal(parseActionItemAccountabilityFilter("unknown"), null);
});

test("follow-up reasons have readable labels", () => {
  assert.deepEqual(
    [
      "overdue",
      "due_today",
      "due_soon",
      "high_priority",
      "missing_due_date",
      "due_later",
    ].map(getActionItemFollowUpReasonLabel),
    [
      "Overdue",
      "Due today",
      "Due soon",
      "High priority",
      "Missing due date",
      "Due later",
    ],
  );
  assert.equal(getActionItemFollowUpReasonLabel(null), null);
});

test("follow-up meeting links retain existing meeting-detail navigation", () => {
  assert.equal(
    buildActionItemMeetingHref("meeting-123"),
    "/dashboard/meetings/meeting-123",
  );
  assert.equal(
    buildActionItemMeetingHref("meeting/id"),
    "/dashboard/meetings/meeting%2Fid",
  );
});

test("meeting search and status changes preserve accountability URL state", () => {
  const href = buildDashboardFilterHref(
    "q=old&status=processing&actionItemStatus=overdue&actionItemsPage=3",
    "new search",
    "failed",
  );
  const query = new URLSearchParams(href.split("?")[1]);

  assert.equal(query.get("q"), "new search");
  assert.equal(query.get("status"), "failed");
  assert.equal(query.get("actionItemStatus"), "overdue");
  assert.equal(query.has("actionItemsPage"), false);
});
