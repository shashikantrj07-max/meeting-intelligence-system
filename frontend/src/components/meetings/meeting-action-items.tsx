"use client";

import { useCallback, useEffect, useState } from "react";

import {
  findTrackedActionItem,
  isMeetingActionItemStatus,
  type GeneratedActionItem,
  type TrackedActionItem,
} from "@/lib/meeting-action-items-shared";
import {
  syncMeetingActionItems,
  updateMeetingActionItemStatus,
} from "@/lib/meeting-action-items";
import type { MeetingActionItemStatus } from "@/types/database";

type MeetingActionItemsProps = {
  meetingId: string;
  items: GeneratedActionItem[];
};

const statusLabels: Record<MeetingActionItemStatus, string> = {
  open: "Open",
  in_progress: "In Progress",
  completed: "Completed",
};
const statusOptions: MeetingActionItemStatus[] = [
  "open",
  "in_progress",
  "completed",
];

export function MeetingActionItems({
  meetingId,
  items,
}: MeetingActionItemsProps) {
  const itemsKey = JSON.stringify(items);
  const [trackedItems, setTrackedItems] = useState<TrackedActionItem[]>([]);
  const [loading, setLoading] = useState(items.length > 0);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadTrackedItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setTrackedItems(await syncMeetingActionItems(meetingId));
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Unable to load tracked action items.",
      );
    } finally {
      setLoading(false);
    }
  }, [meetingId]);

  useEffect(() => {
    if (items.length === 0) {
      return;
    }
    let active = true;
    syncMeetingActionItems(meetingId)
      .then((loadedItems) => {
        if (active) {
          setTrackedItems(loadedItems);
        }
      })
      .catch((loadError: unknown) => {
        if (active) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Unable to load tracked action items.",
          );
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [items.length, itemsKey, meetingId]);

  async function changeStatus(
    actionItem: TrackedActionItem,
    status: MeetingActionItemStatus,
  ) {
    const previousStatus = actionItem.status;
    setError(null);
    setTrackedItems((current) =>
      current.map((item) =>
        item.id === actionItem.id ? { ...item, status } : item,
      ),
    );
    setUpdatingId(actionItem.id);

    try {
      const updated = await updateMeetingActionItemStatus(
        meetingId,
        actionItem.id,
        status,
      );
      setTrackedItems((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
    } catch (updateError) {
      setTrackedItems((current) =>
        current.map((item) =>
          item.id === actionItem.id
            ? { ...item, status: previousStatus }
            : item,
        ),
      );
      setError(
        updateError instanceof Error
          ? updateError.message
          : "Unable to update action-item status.",
      );
    } finally {
      setUpdatingId(null);
    }
  }

  const completedCount = items.filter(
    (item) => findTrackedActionItem(item.text, trackedItems)?.status === "completed",
  ).length;

  return (
    <section>
      <h3 className="text-sm font-semibold text-zinc-900">Action Items</h3>

      {items.length === 0 ? (
        <p className="mt-2 text-sm text-zinc-600">None recorded.</p>
      ) : (
        <>
          {loading ? (
            <p className="mt-2 text-sm text-zinc-600" role="status">
              Loading action-item status...
            </p>
          ) : error ? (
            <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              <p role="alert">
                Action-item tracking is temporarily unavailable. Generated
                action items remain visible.
              </p>
              <p className="mt-1">{error}</p>
              <button
                className="mt-2 font-medium underline"
                onClick={() => void loadTrackedItems()}
                type="button"
              >
                Retry
              </button>
            </div>
          ) : (
            <>
              <p className="mt-2 text-sm text-zinc-600" role="status">
                {completedCount === items.length
                  ? "All action items completed."
                  : completedCount === 0
                    ? "No action items completed yet."
                    : `${completedCount} of ${items.length} action items completed.`}
              </p>
            </>
          )}
          <ul className="mt-3 space-y-3">
            {items.map((item, index) => {
              const trackedItem = findTrackedActionItem(item.text, trackedItems);
              const completed = trackedItem?.status === "completed";
              return (
                <li
                  className={`rounded-lg border p-4 ${
                    completed
                      ? "border-emerald-200 bg-emerald-50"
                      : "border-zinc-200 bg-zinc-50"
                  }`}
                  key={`${item.text}-${index}`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <p className="min-w-0 flex-1 whitespace-pre-wrap break-words text-sm leading-6 text-zinc-800">
                      {item.text}
                    </p>
                    {trackedItem ? (
                      <label className="flex items-center gap-2 text-xs font-medium text-zinc-700">
                        Status
                        <select
                          aria-label={`Status for ${item.text}`}
                          className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs"
                          disabled={
                            loading || updatingId === trackedItem.id
                          }
                          onChange={(event) => {
                            const status = event.currentTarget.value;
                            if (isMeetingActionItemStatus(status)) {
                              void changeStatus(trackedItem, status);
                            }
                          }}
                          value={trackedItem.status}
                        >
                          {statusOptions.map((status) => (
                            <option key={status} value={status}>
                              {statusLabels[status]}
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : (
                      <span className="text-xs text-zinc-600">
                        Status: {loading ? "Loading..." : "Unavailable"}
                      </span>
                    )}
                  </div>
                  {item.owner ? (
                    <p className="mt-2 text-xs text-zinc-600">
                      <span className="font-medium text-zinc-700">Owner:</span>{" "}
                      {item.owner}
                    </p>
                  ) : null}
                  {item.due_date ? (
                    <p className="mt-1 text-xs text-zinc-600">
                      <span className="font-medium text-zinc-700">Due:</span>{" "}
                      {item.due_date}
                    </p>
                  ) : null}
                  {item.priority ? (
                    <p className="mt-1 text-xs text-zinc-600">
                      <span className="font-medium text-zinc-700">
                        Priority:
                      </span>{" "}
                      {item.priority}
                    </p>
                  ) : null}
                  {item.evidence ? (
                    <p className="mt-2 whitespace-pre-wrap break-words text-xs leading-5 text-zinc-600">
                      <span className="font-medium text-zinc-700">
                        Supporting transcript evidence:
                      </span>{" "}
                      <span className="italic">{item.evidence}</span>
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}
