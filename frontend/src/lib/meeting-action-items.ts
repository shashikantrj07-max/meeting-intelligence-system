"use client";

import { createClient } from "@/lib/supabase/client";
import type { MeetingActionItemStatus } from "@/types/database";
import {
  actionItemsResponseError,
  isTrackedActionItem,
  parseActionItemSignalReviewResponse,
  parseActionItemHistoryResponse,
  parseActionItemReviewAnalytics,
  parseTrackedActionItems,
  type MeetingActionItemReviewAnalytics,
  type MeetingActionItemSignalReviewResponse,
  type MeetingActionItemHistoryResponse,
  type TrackedActionItem,
} from "@/lib/meeting-action-items-shared";

export type MeetingActionItemUpdate = {
  status?: MeetingActionItemStatus;
  owner?: string | null;
  due_date?: string | null;
  priority?: string | null;
};

export async function syncMeetingActionItems(
  meetingId: string,
): Promise<TrackedActionItem[]> {
  const response = await actionItemsRequest(
    `${encodeURIComponent(meetingId)}/action-items/sync`,
    "POST",
  );
  const body = await readResponseBody(response);

  if (!response.ok) {
    throw new Error(
      actionItemsResponseError(body, "Unable to load tracked action items."),
    );
  }

  return parseTrackedActionItems(body);
}

export async function getMeetingActionItemHistory(
  meetingId: string,
  actionItemId: string,
): Promise<MeetingActionItemHistoryResponse> {
  const response = await actionItemsRequest(
    `${encodeURIComponent(meetingId)}/action-items/${encodeURIComponent(actionItemId)}/history`,
    "GET",
  );
  const body = await readResponseBody(response);

  if (!response.ok) {
    throw new Error(
      actionItemsResponseError(body, "Unable to load action-item history."),
    );
  }

  return parseActionItemHistoryResponse(body);
}

export async function getActionItemReviewAnalytics(): Promise<MeetingActionItemReviewAnalytics> {
  const response = await actionItemsRequest(
    "action-items/review-analytics",
    "GET",
  );
  const body = await readResponseBody(response);

  if (!response.ok) {
    throw new Error(
      actionItemsResponseError(
        body,
        "Unable to load action-item review analytics.",
      ),
    );
  }

  return parseActionItemReviewAnalytics(body);
}

export async function updateMeetingActionItem(
  meetingId: string,
  actionItemId: string,
  update: MeetingActionItemUpdate,
): Promise<TrackedActionItem> {
  const response = await actionItemsRequest(
    `${encodeURIComponent(meetingId)}/action-items/${encodeURIComponent(actionItemId)}`,
    "PATCH",
    update,
  );
  const body = await readResponseBody(response);

  if (!response.ok) {
    throw new Error(
      actionItemsResponseError(
        body,
        "Unable to update action item.",
      ),
    );
  }

  if (!isTrackedActionItem(body)) {
    throw new Error("The server returned an invalid action-item record.");
  }

  return body;
}

export async function reviewMeetingActionItemSignals(
  meetingId: string,
  actionItemId: string,
): Promise<MeetingActionItemSignalReviewResponse> {
  const response = await actionItemsRequest(
    `${encodeURIComponent(meetingId)}/action-items/${encodeURIComponent(actionItemId)}/review`,
    "POST",
  );
  const body = await readResponseBody(response);

  if (!response.ok) {
    throw new Error(
      actionItemsResponseError(
        body,
        "Unable to mark action-item signals as reviewed.",
      ),
    );
  }

  return parseActionItemSignalReviewResponse(body);
}

export async function updateMeetingActionItemStatus(
  meetingId: string,
  actionItemId: string,
  status: MeetingActionItemStatus,
): Promise<TrackedActionItem> {
  return updateMeetingActionItem(meetingId, actionItemId, { status });
}

async function actionItemsRequest(
  path: string,
  method: "GET" | "POST" | "PATCH",
  body?: MeetingActionItemUpdate,
): Promise<Response> {
  const supabase = createClient();
  const {
    data: { session },
    error: sessionError,
  } = await supabase.auth.getSession();

  if (sessionError) {
    throw new Error(sessionError.message);
  }
  if (!session?.access_token) {
    throw new Error("You must be signed in to access action items.");
  }

  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!baseUrl) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL is not configured.");
  }

  return fetch(
    `${baseUrl.replace(/\/+$/, "")}/api/meetings/${path}`,
    {
      method,
      headers: {
        Authorization: `Bearer ${session.access_token}`,
        "Content-Type": "application/json",
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    },
  );
}

async function readResponseBody(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}
