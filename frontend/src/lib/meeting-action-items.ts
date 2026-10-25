"use client";

import { createClient } from "@/lib/supabase/client";
import type { MeetingActionItemStatus } from "@/types/database";
import {
  actionItemsResponseError,
  isTrackedActionItem,
  parseTrackedActionItems,
  type TrackedActionItem,
} from "@/lib/meeting-action-items-shared";

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

export async function updateMeetingActionItemStatus(
  meetingId: string,
  actionItemId: string,
  status: MeetingActionItemStatus,
): Promise<TrackedActionItem> {
  const response = await actionItemsRequest(
    `${encodeURIComponent(meetingId)}/action-items/${encodeURIComponent(actionItemId)}`,
    "PATCH",
    { status },
  );
  const body = await readResponseBody(response);

  if (!response.ok) {
    throw new Error(
      actionItemsResponseError(
        body,
        "Unable to update action-item status.",
      ),
    );
  }

  if (!isTrackedActionItem(body)) {
    throw new Error("The server returned an invalid action-item record.");
  }

  return body;
}

async function actionItemsRequest(
  path: string,
  method: "POST" | "PATCH",
  body?: { status: MeetingActionItemStatus },
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
    throw new Error("You must be signed in to update action items.");
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
