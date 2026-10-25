import type { Json, MeetingActionItemStatus } from "@/types/database";

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
  created_at: string;
  updated_at: string;
};

const actionItemStatuses: MeetingActionItemStatus[] = [
  "open",
  "in_progress",
  "completed",
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

function optionalString(value: Json | undefined): string | null {
  return typeof value === "string" ? value : null;
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
    "created_at" in value &&
    typeof value.created_at === "string" &&
    "updated_at" in value &&
    typeof value.updated_at === "string"
  );
}
