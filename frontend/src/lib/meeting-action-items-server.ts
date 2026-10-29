import { createClient } from "@/lib/supabase/server";
import type {
  ActionItemAccountabilitySignal,
  ActionItemAccountabilityFilter,
  ActionItemFollowUpReason,
  ActionItemReviewStateFilter,
} from "@/lib/dashboard-accountability";
import { parseActionItemAccountabilitySignal } from "@/lib/dashboard-accountability";
import {
  parseActionItemReviewAnalytics,
  type MeetingActionItemReviewAnalytics,
} from "@/lib/meeting-action-items-shared";

export type ActionItemAccountabilitySummary = {
  total: number;
  open: number;
  in_progress: number;
  completed: number;
  overdue: number;
};

export type ActionItemReviewAnalyticsResult = {
  data: MeetingActionItemReviewAnalytics | null;
  error: Error | null;
};

export type ActionItemAccountabilityRecord = {
  id: string;
  meeting_id: string;
  meeting_title: string;
  text: string;
  owner: string | null;
  due_date: string | null;
  priority: string | null;
  status: "open" | "in_progress" | "completed";
  is_overdue: boolean;
  attention_reason:
    | "overdue"
    | "due_soon"
    | "due_later"
    | "no_usable_due_date"
    | "completed";
  follow_up_reason: ActionItemFollowUpReason | null;
  accountability_signals: ActionItemAccountabilitySignal[];
  reviewed_at: string | null;
  needs_review: boolean;
};

export type ActionItemAccountabilityItems = {
  items: ActionItemAccountabilityRecord[];
  page: number;
  page_size: number;
  has_more: boolean;
};

export async function getActionItemAccountabilitySummary(): Promise<{
  data: ActionItemAccountabilitySummary | null;
  error: Error | null;
}> {
  const supabase = await createClient();
  const {
    data: { session },
    error: sessionError,
  } = await supabase.auth.getSession();

  if (sessionError) {
    return { data: null, error: sessionError };
  }
  if (!session?.access_token) {
    return {
      data: null,
      error: new Error("A signed-in session is required for this summary."),
    };
  }

  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!baseUrl) {
    return {
      data: null,
      error: new Error("NEXT_PUBLIC_API_BASE_URL is not configured."),
    };
  }

  try {
    const response = await fetch(
      `${baseUrl.replace(/\/+$/, "")}/api/meetings/action-items/accountability-summary`,
      {
        headers: { Authorization: `Bearer ${session.access_token}` },
        cache: "no-store",
      },
    );
    const body: unknown = await response.json();

    if (!response.ok) {
      return {
        data: null,
        error: new Error(readErrorDetail(body)),
      };
    }
    if (!isActionItemAccountabilitySummary(body)) {
      return {
        data: null,
        error: new Error("The server returned an invalid accountability summary."),
      };
    }

    return { data: body, error: null };
  } catch (error) {
    return {
      data: null,
      error:
        error instanceof Error
          ? error
          : new Error("Unable to load action-item accountability."),
    };
  }
}

export async function getActionItemReviewAnalytics(): Promise<ActionItemReviewAnalyticsResult> {
  let supabase: Awaited<ReturnType<typeof createClient>>;
  try {
    supabase = await createClient();
  } catch {
    return {
      data: null,
      error: new Error("Unable to initialize review analytics."),
    };
  }
  let accessToken: string | null;
  let sessionError: Error | null;
  try {
    const {
      data: { session },
      error,
    } = await supabase.auth.getSession();
    sessionError = error;
    accessToken = session?.access_token ?? null;
  } catch {
    return {
      data: null,
      error: new Error("Unable to authenticate the review analytics request."),
    };
  }

  if (sessionError) {
    return { data: null, error: sessionError };
  }
  if (!accessToken) {
    return {
      data: null,
      error: new Error("A signed-in session is required for review analytics."),
    };
  }

  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!baseUrl) {
    return {
      data: null,
      error: new Error("NEXT_PUBLIC_API_BASE_URL is not configured."),
    };
  }

  try {
    const response = await fetch(
      `${baseUrl.replace(/\/+$/, "")}/api/meetings/action-items/review-analytics`,
      {
        headers: { Authorization: `Bearer ${accessToken}` },
        cache: "no-store",
      },
    );
    const body: unknown = await response.json();

    if (!response.ok) {
      return { data: null, error: new Error(readErrorDetail(body)) };
    }

    return {
      data: parseActionItemReviewAnalytics(body),
      error: null,
    };
  } catch (error) {
    return {
      data: null,
      error:
        error instanceof Error
          ? error
          : new Error("Unable to load action-item review analytics."),
    };
  }
}

export async function getActionItemAccountabilityItems(
  filter: ActionItemAccountabilityFilter,
  page: number,
  reviewState: ActionItemReviewStateFilter = "all",
): Promise<{
  data: ActionItemAccountabilityItems | null;
  error: Error | null;
}> {
  const supabase = await createClient();
  const {
    data: { session },
    error: sessionError,
  } = await supabase.auth.getSession();
  if (sessionError) {
    return { data: null, error: sessionError };
  }
  if (!session?.access_token) {
    return {
      data: null,
      error: new Error("A signed-in session is required for accountability data."),
    };
  }

  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!baseUrl) {
    return {
      data: null,
      error: new Error("NEXT_PUBLIC_API_BASE_URL is not configured."),
    };
  }
  const query = new URLSearchParams({
    status: filter,
    review_state: reviewState,
    page: String(page),
  });

  try {
    const response = await fetch(
      `${baseUrl.replace(/\/+$/, "")}/api/meetings/action-items/accountability-items?${query}`,
      {
        headers: { Authorization: `Bearer ${session.access_token}` },
        cache: "no-store",
      },
    );
    const body: unknown = await response.json();
    if (!response.ok) {
      return { data: null, error: new Error(readErrorDetail(body)) };
    }
    if (!isActionItemAccountabilityItems(body)) {
      return {
        data: null,
        error: new Error("The server returned invalid accountability items."),
      };
    }
    return { data: body, error: null };
  } catch (error) {
    return {
      data: null,
      error:
        error instanceof Error
          ? error
          : new Error("Unable to load action-item accountability items."),
    };
  }
}

function isActionItemAccountabilitySummary(
  value: unknown,
): value is ActionItemAccountabilitySummary {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const summary = value as Record<string, unknown>;
  return (
    isCount(summary.total) &&
    isCount(summary.open) &&
    isCount(summary.in_progress) &&
    isCount(summary.completed) &&
    isCount(summary.overdue) &&
    summary.open + summary.in_progress + summary.completed === summary.total &&
    summary.overdue <= summary.total
  );
}

function isActionItemAccountabilityItems(
  value: unknown,
): value is ActionItemAccountabilityItems {
  if (typeof value !== "object" || value === null || !("items" in value)) {
    return false;
  }
  const response = value as Record<string, unknown>;
  return (
    Array.isArray(response.items) &&
    response.items.every(isActionItemAccountabilityRecord) &&
    isCount(response.page) &&
    response.page > 0 &&
    isCount(response.page_size) &&
    response.page_size > 0 &&
    typeof response.has_more === "boolean"
  );
}

function isActionItemAccountabilityRecord(
  value: unknown,
): value is ActionItemAccountabilityRecord {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const item = value as Record<string, unknown>;
  return (
    typeof item.id === "string" &&
    typeof item.meeting_id === "string" &&
    typeof item.meeting_title === "string" &&
    typeof item.text === "string" &&
    (typeof item.owner === "string" || item.owner === null) &&
    (typeof item.due_date === "string" || item.due_date === null) &&
    (typeof item.priority === "string" || item.priority === null) &&
    (item.status === "open" ||
      item.status === "in_progress" ||
      item.status === "completed") &&
    typeof item.is_overdue === "boolean" &&
    (item.attention_reason === "overdue" ||
      item.attention_reason === "due_soon" ||
      item.attention_reason === "due_later" ||
      item.attention_reason === "no_usable_due_date" ||
      item.attention_reason === "completed") &&
    (item.follow_up_reason === null ||
      item.follow_up_reason === "overdue" ||
      item.follow_up_reason === "due_today" ||
      item.follow_up_reason === "due_soon" ||
      item.follow_up_reason === "high_priority" ||
      item.follow_up_reason === "missing_due_date" ||
      item.follow_up_reason === "due_later") &&
    Array.isArray(item.accountability_signals) &&
    item.accountability_signals.every(
      (signal) => parseActionItemAccountabilitySignal(signal) !== null,
    ) &&
    (typeof item.reviewed_at === "string" || item.reviewed_at === null) &&
    typeof item.needs_review === "boolean"
  );
}

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function readErrorDetail(value: unknown): string {
  if (
    typeof value === "object" &&
    value !== null &&
    "detail" in value &&
    typeof value.detail === "string"
  ) {
    return value.detail;
  }
  return "Unable to load action-item accountability.";
}
