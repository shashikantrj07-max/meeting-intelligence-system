import type {
  Json,
  MeetingActionItemAccountabilitySignal,
  MeetingActionItemHistoryField,
  MeetingActionItemStatus,
} from "@/types/database";

export type GeneratedActionItem = {
  text: string;
  owner: string | null;
  due_date: string | null;
  priority: string | null;
  evidence: string | null;
};

export type TrackedActionItem = GeneratedActionItem & {
  id: string;
  meeting_id: string;
  identity_key: string;
  status: MeetingActionItemStatus;
  is_overdue: boolean;
  created_at: string;
  updated_at: string;
};

export type MeetingActionItemHistoryRecord = {
  id: string;
  action_item_id: string;
  meeting_id: string;
  action_item_text: string;
  field_changed: MeetingActionItemHistoryField;
  previous_value: string | null;
  new_value: string | null;
  changed_at: string;
};

export type MeetingActionItemHistoryResponse = {
  items: MeetingActionItemHistoryRecord[];
  accountability_signals: MeetingActionItemAccountabilitySignal[];
  reviewed_at: string | null;
  needs_review: boolean;
};

export type MeetingActionItemReviewAnalytics = {
  total_reviewable: number;
  reviewed: number;
  needs_review: number;
  reopened_since_review: number;
  review_coverage_percent: number;
};

export type ActionItemReviewAnalyticsMetric = {
  key:
    | "total_reviewable"
    | "reviewed"
    | "needs_review"
    | "reopened_since_review"
    | "review_coverage_percent";
  label: string;
  value: string;
  description: string;
};

export type ActionItemReviewAnalyticsState =
  | "loading"
  | "error"
  | "empty"
  | "loaded";

export type ActionItemFilter =
  | "all"
  | MeetingActionItemStatus
  | "overdue";

export type GeneratedActionItemWithTracking = {
  generated: GeneratedActionItem;
  tracked: TrackedActionItem | undefined;
};

const actionItemStatuses: MeetingActionItemStatus[] = [
  "open",
  "in_progress",
  "completed",
];
const actionItemHistoryFields: MeetingActionItemHistoryField[] = [
  "status",
  "owner",
  "due_date",
  "priority",
];

export function isMeetingActionItemStatus(
  value: string,
): value is MeetingActionItemStatus {
  return actionItemStatuses.some((status) => status === value);
}

export function parseGeneratedActionItems(value: Json): GeneratedActionItem[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.flatMap((item) => {
    if (
      typeof item !== "object" ||
      item === null ||
      Array.isArray(item) ||
      typeof item.text !== "string" ||
      item.text.trim().length === 0
    ) {
      return [];
    }

    return [
      {
        text: item.text.trim(),
        owner: optionalString(item.owner),
        due_date: optionalString(item.due_date),
        priority: optionalString(item.priority),
        evidence: optionalString(item.evidence),
      },
    ];
  });
}

export function normalizeActionItemText(text: string): string {
  return text.trim().replace(/\s+/g, " ").toLowerCase();
}

export function findTrackedActionItem(
  text: string,
  trackedItems: TrackedActionItem[],
): TrackedActionItem | undefined {
  const normalizedText = normalizeActionItemText(text);
  return trackedItems.find(
    (item) => normalizeActionItemText(item.text) === normalizedText,
  );
}

export function filterGeneratedActionItems(
  items: GeneratedActionItem[],
  trackedItems: TrackedActionItem[],
  filter: ActionItemFilter,
): GeneratedActionItemWithTracking[] {
  return items
    .map((generated) => ({
      generated,
      tracked: findTrackedActionItem(generated.text, trackedItems),
    }))
    .filter(({ tracked }) => {
      if (filter === "all") {
        return true;
      }
      if (filter === "overdue") {
        return tracked?.is_overdue === true && tracked.status !== "completed";
      }
      return tracked?.status === filter;
    });
}

export function parseTrackedActionItems(value: unknown): TrackedActionItem[] {
  if (
    typeof value !== "object" ||
    value === null ||
    !("items" in value) ||
    !Array.isArray(value.items) ||
    !value.items.every(isTrackedActionItem)
  ) {
    throw new Error("The server returned invalid tracked action items.");
  }
  return value.items;
}

export function actionItemsResponseError(
  value: unknown,
  fallback: string,
): string {
  if (
    typeof value === "object" &&
    value !== null &&
    "detail" in value &&
    typeof value.detail === "string"
  ) {
    return value.detail;
  }
  return fallback;
}

export type MeetingActionItemSignalReviewResponse = {
  reviewed_at: string;
  needs_review: false;
};

export function parseActionItemSignalReviewResponse(
  value: unknown,
): MeetingActionItemSignalReviewResponse {
  if (
    typeof value !== "object" ||
    value === null ||
    !("reviewed_at" in value) ||
    typeof value.reviewed_at !== "string" ||
    Number.isNaN(Date.parse(value.reviewed_at)) ||
    !("needs_review" in value) ||
    value.needs_review !== false
  ) {
    throw new Error("The server returned an invalid action-item review.");
  }
  return {
    reviewed_at: value.reviewed_at,
    needs_review: false,
  };
}

export function parseActionItemReviewAnalytics(
  value: unknown,
): MeetingActionItemReviewAnalytics {
  if (
    typeof value !== "object" ||
    value === null ||
    Array.isArray(value) ||
    Object.keys(value).length !== 5 ||
    !("total_reviewable" in value) ||
    !isNonNegativeInteger(value.total_reviewable) ||
    !("reviewed" in value) ||
    !isNonNegativeInteger(value.reviewed) ||
    !("needs_review" in value) ||
    !isNonNegativeInteger(value.needs_review) ||
    !("reopened_since_review" in value) ||
    !isNonNegativeInteger(value.reopened_since_review) ||
    !("review_coverage_percent" in value) ||
    typeof value.review_coverage_percent !== "number" ||
    !Number.isFinite(value.review_coverage_percent) ||
    value.review_coverage_percent < 0 ||
    value.review_coverage_percent > 100 ||
    !Number.isInteger(value.review_coverage_percent * 10) ||
    value.reviewed + value.needs_review !== value.total_reviewable ||
    value.reopened_since_review > value.needs_review ||
    (value.total_reviewable === 0 && value.review_coverage_percent !== 0)
  ) {
    throw new Error("The server returned invalid action-item review analytics.");
  }
  return {
    total_reviewable: value.total_reviewable,
    reviewed: value.reviewed,
    needs_review: value.needs_review,
    reopened_since_review: value.reopened_since_review,
    review_coverage_percent: value.review_coverage_percent,
  };
}

export function getActionItemReviewAnalyticsMetrics(
  analytics: MeetingActionItemReviewAnalytics,
): ActionItemReviewAnalyticsMetric[] {
  return [
    {
      key: "total_reviewable",
      label: "Total reviewable",
      value: String(analytics.total_reviewable),
      description: "Items with current accountability signals.",
    },
    {
      key: "reviewed",
      label: "Reviewed",
      value: String(analytics.reviewed),
      description: "Acknowledged through their latest reviewed history.",
    },
    {
      key: "needs_review",
      label: "Needs review",
      value: String(analytics.needs_review),
      description: "No review yet, or newer meaningful activity exists.",
    },
    {
      key: "reopened_since_review",
      label: "Reopened since review",
      value: String(analytics.reopened_since_review),
      description: "Reviewed items with newer meaningful activity.",
    },
    {
      key: "review_coverage_percent",
      label: "Review coverage",
      value: `${analytics.review_coverage_percent.toFixed(1)}%`,
      description: "Reviewed divided by total reviewable.",
    },
  ];
}

export function getActionItemReviewAnalyticsState(
  loading: boolean,
  error: string | null,
  analytics: MeetingActionItemReviewAnalytics | null,
): ActionItemReviewAnalyticsState {
  if (loading) {
    return "loading";
  }
  if (error) {
    return "error";
  }
  return analytics ? "loaded" : "empty";
}

export function parseActionItemHistoryResponse(
  value: unknown,
): MeetingActionItemHistoryResponse {
  if (
    typeof value !== "object" ||
    value === null ||
    !("items" in value) ||
    !Array.isArray(value.items) ||
    !value.items.every(isMeetingActionItemHistoryRecord) ||
    !("accountability_signals" in value) ||
    !Array.isArray(value.accountability_signals) ||
    !value.accountability_signals.every(isMeetingActionItemAccountabilitySignal) ||
    !("reviewed_at" in value) ||
    (typeof value.reviewed_at !== "string" && value.reviewed_at !== null) ||
    !("needs_review" in value) ||
    typeof value.needs_review !== "boolean"
  ) {
    throw new Error("The server returned invalid action-item history.");
  }
  return {
    items: value.items,
    accountability_signals: value.accountability_signals,
    reviewed_at: value.reviewed_at,
    needs_review: value.needs_review,
  };
}

export function getMeetingActionItemAccountabilitySignalLabel(
  signal: MeetingActionItemAccountabilitySignal,
): string {
  switch (signal) {
    case "reopened":
      return "Reopened";
    case "repeated_updates":
      return "Repeated updates";
    case "stale":
      return "Stale";
    case "recent_activity":
      return "Recent activity";
  }
}

function isMeetingActionItemAccountabilitySignal(
  value: unknown,
): value is MeetingActionItemAccountabilitySignal {
  return (
    value === "reopened" ||
    value === "repeated_updates" ||
    value === "stale" ||
    value === "recent_activity"
  );
}

export function getActionItemHistoryFieldLabel(
  field: MeetingActionItemHistoryField,
): string {
  switch (field) {
    case "status":
      return "Status";
    case "owner":
      return "Owner";
    case "due_date":
      return "Due date";
    case "priority":
      return "Priority";
  }
}

export function getActionItemHistoryValue(value: string | null): string {
  return value?.trim() ? value : "Not set";
}

export function getActionItemHistoryTimestamp(value: string): string {
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime())
    ? value
    : timestamp.toLocaleString();
}

export function getActionItemHistoryState(
  loading: boolean,
  error: string | null,
  records: MeetingActionItemHistoryRecord[],
): "loading" | "error" | "empty" | "records" {
  if (loading) {
    return "loading";
  }
  if (error) {
    return "error";
  }
  return records.length === 0 ? "empty" : "records";
}

function optionalString(value: Json | undefined): string | null {
  return typeof value === "string" ? value : null;
}

function isNonNegativeInteger(value: unknown): value is number {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    value >= 0
  );
}

function isMeetingActionItemHistoryRecord(
  value: unknown,
): value is MeetingActionItemHistoryRecord {
  return (
    typeof value === "object" &&
    value !== null &&
    "id" in value &&
    typeof value.id === "string" &&
    "action_item_id" in value &&
    typeof value.action_item_id === "string" &&
    "meeting_id" in value &&
    typeof value.meeting_id === "string" &&
    "action_item_text" in value &&
    typeof value.action_item_text === "string" &&
    value.action_item_text.trim().length > 0 &&
    "field_changed" in value &&
    typeof value.field_changed === "string" &&
    actionItemHistoryFields.includes(
      value.field_changed as MeetingActionItemHistoryField,
    ) &&
    "previous_value" in value &&
    (typeof value.previous_value === "string" || value.previous_value === null) &&
    "new_value" in value &&
    (typeof value.new_value === "string" || value.new_value === null) &&
    "changed_at" in value &&
    typeof value.changed_at === "string" &&
    value.changed_at.length > 0
  );
}

export function isTrackedActionItem(value: unknown): value is TrackedActionItem {
  return (
    typeof value === "object" &&
    value !== null &&
    "id" in value &&
    typeof value.id === "string" &&
    "meeting_id" in value &&
    typeof value.meeting_id === "string" &&
    "identity_key" in value &&
    typeof value.identity_key === "string" &&
    "text" in value &&
    typeof value.text === "string" &&
    "status" in value &&
    typeof value.status === "string" &&
    isMeetingActionItemStatus(value.status) &&
    "is_overdue" in value &&
    typeof value.is_overdue === "boolean" &&
    "created_at" in value &&
    typeof value.created_at === "string" &&
    "updated_at" in value &&
    typeof value.updated_at === "string"
  );
}
