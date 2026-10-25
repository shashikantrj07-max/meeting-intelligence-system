import type {
  DashboardFilters,
  DashboardStatusFilter,
} from "@/lib/dashboard-meetings";

export type ActionItemAccountabilityFilter =
  | "all"
  | "open"
  | "in_progress"
  | "completed"
  | "overdue"
  | "needs_attention"
  | "follow_up";

const accountabilityFilters: ActionItemAccountabilityFilter[] = [
  "all",
  "open",
  "in_progress",
  "completed",
  "overdue",
  "needs_attention",
  "follow_up",
];

export type ActionItemFollowUpReason =
  | "overdue"
  | "due_today"
  | "due_soon"
  | "high_priority"
  | "missing_due_date"
  | "due_later";

const followUpReasonLabels: Record<ActionItemFollowUpReason, string> = {
  overdue: "Overdue",
  due_today: "Due today",
  due_soon: "Due soon",
  high_priority: "High priority",
  missing_due_date: "Missing due date",
  due_later: "Due later",
};

export function parseActionItemAccountabilityFilter(
  value: string | string[] | undefined,
): ActionItemAccountabilityFilter | null {
  if (typeof value !== "string") {
    return null;
  }
  return accountabilityFilters.find((filter) => filter === value) ?? null;
}

export function getActionItemFollowUpReasonLabel(
  reason: ActionItemFollowUpReason | null,
): string | null {
  return reason === null ? null : followUpReasonLabels[reason];
}

export function buildActionItemMeetingHref(meetingId: string): string {
  return `/dashboard/meetings/${encodeURIComponent(meetingId)}`;
}

export function parseActionItemsPage(
  value: string | string[] | undefined,
): number {
  if (
    typeof value !== "string" ||
    !/^[1-9]\d*$/.test(value)
  ) {
    return 1;
  }
  const page = Number(value);
  return Number.isSafeInteger(page) && page <= 100_000 ? page : 1;
}

export function buildActionItemAccountabilityHref(
  filters: DashboardFilters,
  accountabilityFilter: ActionItemAccountabilityFilter,
  page = 1,
): string {
  const query = new URLSearchParams();
  if (filters.search) {
    query.set("q", filters.search);
  }
  if (filters.status !== "all") {
    query.set("status", filters.status);
  }
  query.set("actionItemStatus", accountabilityFilter);
  if (page > 1) {
    query.set("actionItemsPage", String(page));
  }
  return `/dashboard?${query.toString()}`;
}

export function buildDashboardFilterHref(
  currentQuery: string,
  search: string,
  status: string,
): string {
  const query = new URLSearchParams(currentQuery);
  const normalizedSearch = search.trim().slice(0, 200);
  const normalizedStatus = isDashboardStatusFilter(status) ? status : "all";

  if (normalizedSearch) {
    query.set("q", normalizedSearch);
  } else {
    query.delete("q");
  }
  if (normalizedStatus !== "all") {
    query.set("status", normalizedStatus);
  } else {
    query.delete("status");
  }
  query.delete("actionItemsPage");

  const queryString = query.toString();
  return queryString ? `/dashboard?${queryString}` : "/dashboard";
}

function isDashboardStatusFilter(
  value: string,
): value is DashboardStatusFilter {
  return (
    value === "all" ||
    value === "processing" ||
    value === "completed" ||
    value === "failed"
  );
}
