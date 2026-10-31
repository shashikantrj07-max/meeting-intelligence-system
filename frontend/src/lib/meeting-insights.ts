import { createClient } from "@/lib/supabase/client";

type GenerateMeetingInsightsResponse = {
  meeting_id: string;
  job_id: string;
  stage: "pending" | "running" | "retrying" | "completed" | "failed";
  job_status: "pending" | "running" | "retrying" | "completed" | "failed";
};

export async function generateMeetingInsights(
  meetingId: string,
): Promise<GenerateMeetingInsightsResponse> {
  const supabase = createClient();

  const {
    data: { session },
    error: sessionError,
  } = await supabase.auth.getSession();

  if (sessionError) {
    throw new Error(sessionError.message);
  }

  if (!session?.access_token) {
    throw new Error("You must be signed in to generate meeting intelligence.");
  }

  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  if (!baseUrl) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL is not configured.");
  }

  const response = await fetch(
    `${baseUrl}/api/meetings/${encodeURIComponent(meetingId)}/insights`,
    {
      method: "POST",
      headers: {
        "Idempotency-Key": crypto.randomUUID(),
        Authorization: `Bearer ${session.access_token}`,
      },
    },
  );

  if (!response.ok) {
    let message = "Failed to generate meeting intelligence.";

    try {
      const body = (await response.json()) as { detail?: string };

      if (body.detail) {
        message = body.detail;
      }
    } catch {
      // Keep the generic message when the backend response is not JSON.
    }

    throw new Error(message);
  }

  return (await response.json()) as GenerateMeetingInsightsResponse;
}