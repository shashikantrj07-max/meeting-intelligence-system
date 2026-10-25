import { createClient } from "@/lib/supabase/server";

export type ActionItemAccountabilitySummary = {
  total: number;
  open: number;
  in_progress: number;
  completed: number;
  overdue: number;
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
