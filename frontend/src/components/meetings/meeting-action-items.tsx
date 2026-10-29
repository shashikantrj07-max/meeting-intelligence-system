"use client";

import { useCallback, useEffect, useState } from "react";

import { ActionItemSignalReviewButton } from "@/components/meetings/action-item-signal-review-button";
import {
  filterGeneratedActionItems,
  findTrackedActionItem,
  getActionItemHistoryFieldLabel,
  getActionItemHistoryState,
  getActionItemHistoryTimestamp,
  getActionItemHistoryValue,
  getMeetingActionItemAccountabilitySignalLabel,
  isMeetingActionItemStatus,
  type ActionItemFilter,
  type GeneratedActionItem,
  type MeetingActionItemHistoryRecord,
  type TrackedActionItem,
} from "@/lib/meeting-action-items-shared";
import {
  getMeetingActionItemHistory,
  syncMeetingActionItems,
  updateMeetingActionItem,
  type MeetingActionItemUpdate,
} from "@/lib/meeting-action-items";
import type {
  MeetingActionItemAccountabilitySignal,
  MeetingActionItemStatus,
} from "@/types/database";

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
const filterOptions: { value: ActionItemFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In Progress" },
  { value: "completed", label: "Completed" },
  { value: "overdue", label: "Overdue" },
];

type MetadataDraft = {
  owner: string;
  due_date: string;
  priority: string;
};

type HistoryState = {
  open: boolean;
  loading: boolean;
  loaded: boolean;
  records: MeetingActionItemHistoryRecord[];
  accountabilitySignals: MeetingActionItemAccountabilitySignal[];
  reviewedAt: string | null;
  needsReview: boolean;
  error: string | null;
};

function metadataDraft(item: TrackedActionItem): MetadataDraft {
  return {
    owner: item.owner ?? "",
    due_date: item.due_date ?? "",
    priority: item.priority ?? "",
  };
}

export function MeetingActionItems({
  meetingId,
  items,
}: MeetingActionItemsProps) {
  const itemsKey = JSON.stringify(items);
  const [trackedItems, setTrackedItems] = useState<TrackedActionItem[]>([]);
  const [metadataDrafts, setMetadataDrafts] = useState<
    Record<string, MetadataDraft>
  >({});
  const [historyStates, setHistoryStates] = useState<
    Record<string, HistoryState>
  >({});
  const [loading, setLoading] = useState(items.length > 0);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<ActionItemFilter>("all");

  const loadTrackedItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const loadedItems = await syncMeetingActionItems(meetingId);
      setTrackedItems(loadedItems);
      setMetadataDrafts(
        Object.fromEntries(
          loadedItems.map((item) => [item.id, metadataDraft(item)]),
        ),
      );
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
          setMetadataDrafts(
            Object.fromEntries(
              loadedItems.map((item) => [item.id, metadataDraft(item)]),
            ),
          );
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

  function changeMetadataDraft(
    actionItem: TrackedActionItem,
    field: keyof MetadataDraft,
    value: string,
  ) {
    setMetadataDrafts((current) => ({
      ...current,
      [actionItem.id]: {
        ...(current[actionItem.id] ?? metadataDraft(actionItem)),
        [field]: value,
      },
    }));
  }

  async function loadHistory(actionItem: TrackedActionItem) {
    setHistoryStates((current) => ({
      ...current,
      [actionItem.id]: {
        open: true,
        loading: true,
        loaded: false,
        records: current[actionItem.id]?.records ?? [],
        accountabilitySignals:
          current[actionItem.id]?.accountabilitySignals ?? [],
        reviewedAt: current[actionItem.id]?.reviewedAt ?? null,
        needsReview: current[actionItem.id]?.needsReview ?? false,
        error: null,
      },
    }));

    try {
      const records = await getMeetingActionItemHistory(
        meetingId,
        actionItem.id,
      );
      setHistoryStates((current) => ({
        ...current,
        [actionItem.id]: {
          open: true,
          loading: false,
          loaded: true,
          records: records.items,
          accountabilitySignals: records.accountability_signals,
          reviewedAt: records.reviewed_at,
          needsReview: records.needs_review,
          error: null,
        },
      }));
    } catch (historyError) {
      setHistoryStates((current) => ({
        ...current,
        [actionItem.id]: {
          open: true,
          loading: false,
          loaded: false,
          records: current[actionItem.id]?.records ?? [],
          accountabilitySignals:
            current[actionItem.id]?.accountabilitySignals ?? [],
          reviewedAt: current[actionItem.id]?.reviewedAt ?? null,
          needsReview: current[actionItem.id]?.needsReview ?? false,
          error:
            historyError instanceof Error
              ? historyError.message
              : "Unable to load action-item history.",
        },
      }));
    }
  }

  function toggleHistory(actionItem: TrackedActionItem) {
    const historyState = historyStates[actionItem.id];
    if (historyState?.open) {
      setHistoryStates((current) => ({
        ...current,
        [actionItem.id]: { ...historyState, open: false },
      }));
    } else if (historyState?.loaded) {
      setHistoryStates((current) => ({
        ...current,
        [actionItem.id]: { ...historyState, open: true },
      }));
    } else {
      void loadHistory(actionItem);
    }
  }

  async function updateActionItem(
    actionItem: TrackedActionItem,
    update: MeetingActionItemUpdate,
  ) {
    const previousItem = actionItem;
    const previousDraft =
      metadataDrafts[actionItem.id] ?? metadataDraft(actionItem);
    const optimisticItem = {
      ...actionItem,
      ...update,
      ...(update.status === "completed" ? { is_overdue: false } : {}),
    };
    setError(null);
    setTrackedItems((current) =>
      current.map((item) =>
        item.id === actionItem.id
          ? optimisticItem
          : item,
      ),
    );
    setMetadataDrafts((current) => ({
      ...current,
      [actionItem.id]: metadataDraft(optimisticItem),
    }));
    setUpdatingId(actionItem.id);

    try {
      const updated = await updateMeetingActionItem(
        meetingId,
        actionItem.id,
        update,
      );
      setTrackedItems((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setMetadataDrafts((current) => ({
        ...current,
        [updated.id]: metadataDraft(updated),
      }));
      if (historyStates[actionItem.id]?.open) {
        void loadHistory(updated);
      }
    } catch (updateError) {
      setTrackedItems((current) =>
        current.map((item) =>
          item.id === actionItem.id
            ? previousItem
            : item,
        ),
      );
      setMetadataDrafts((current) => ({
        ...current,
        [actionItem.id]: previousDraft,
      }));
      setError(
        updateError instanceof Error
          ? updateError.message
          : "Unable to update action item.",
      );
    } finally {
      setUpdatingId(null);
    }
  }

  function saveMetadata(actionItem: TrackedActionItem) {
    const draft =
      metadataDrafts[actionItem.id] ?? metadataDraft(actionItem);
    const update: MeetingActionItemUpdate = {};
    const owner = draft.owner.trim() || null;
    const dueDate = draft.due_date.trim() || null;
    const priority = draft.priority.trim() || null;

    if (owner !== actionItem.owner) {
      update.owner = owner;
    }
    if (dueDate !== actionItem.due_date) {
      update.due_date = dueDate;
    }
    if (priority !== actionItem.priority) {
      update.priority = priority;
    }
    if (Object.keys(update).length > 0) {
      void updateActionItem(actionItem, update);
    }
  }

  const completedCount = items.filter(
    (item) => findTrackedActionItem(item.text, trackedItems)?.status === "completed",
  ).length;
  const visibleItems = filterGeneratedActionItems(items, trackedItems, filter);

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
          <label className="mt-4 flex w-fit items-center gap-2 text-sm font-medium text-zinc-700">
            Filter
            <select
              aria-label="Filter action items"
              className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm"
              disabled={loading || Boolean(error)}
              onChange={(event) => {
                const selected = filterOptions.find(
                  (option) => option.value === event.currentTarget.value,
                );
                setFilter(selected?.value ?? "all");
              }}
              value={filter}
            >
              {filterOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          {visibleItems.length === 0 ? (
            <p className="mt-3 text-sm text-zinc-600">
              No action items match this filter.
            </p>
          ) : (
            <ul className="mt-3 space-y-3">
              {visibleItems.map(({ generated: item, tracked }, index) => {
                const completed = tracked?.status === "completed";
                const overdue = tracked?.is_overdue === true && !completed;
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
                      {tracked ? (
                        <label className="flex items-center gap-2 text-xs font-medium text-zinc-700">
                          Status
                          <select
                            aria-label={`Status for ${item.text}`}
                            className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs"
                            disabled={loading || updatingId === tracked.id}
                            onChange={(event) => {
                              const status = event.currentTarget.value;
                              if (isMeetingActionItemStatus(status)) {
                                void updateActionItem(tracked, { status });
                              }
                            }}
                            value={tracked.status}
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
                    {tracked ? (
                      <>
                        <div className="mt-3 grid gap-3 sm:grid-cols-3">
                          {(
                            [
                              ["owner", "Owner"],
                              ["due_date", "Due date"],
                              ["priority", "Priority"],
                            ] as const
                          ).map(([field, label]) => {
                            const draft =
                              metadataDrafts[tracked.id] ??
                              metadataDraft(tracked);
                            return (
                              <label
                                className="flex flex-col gap-1 text-xs font-medium text-zinc-700"
                                key={field}
                              >
                                {label}
                                <input
                                  aria-label={`${label} for ${item.text}`}
                                  className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-xs font-normal"
                                  disabled={
                                    loading || updatingId === tracked.id
                                  }
                                  onChange={(event) =>
                                    changeMetadataDraft(
                                      tracked,
                                      field,
                                      event.currentTarget.value,
                                    )
                                  }
                                  placeholder={
                                    field === "due_date"
                                      ? "Date or date note"
                                      : `Add ${label.toLowerCase()}`
                                  }
                                  type="text"
                                  value={draft[field]}
                                />
                              </label>
                            );
                          })}
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <button
                            className="rounded-md border border-zinc-300 bg-white px-2.5 py-1 text-xs font-medium text-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
                            disabled={
                              loading ||
                              updatingId === tracked.id ||
                              (() => {
                                const draft =
                                  metadataDrafts[tracked.id] ??
                                  metadataDraft(tracked);
                                return (
                                  (draft.owner.trim() || null) ===
                                    tracked.owner &&
                                  (draft.due_date.trim() || null) ===
                                    tracked.due_date &&
                                  (draft.priority.trim() || null) ===
                                    tracked.priority
                                );
                              })()
                            }
                            onClick={() => saveMetadata(tracked)}
                            type="button"
                          >
                            Save details
                          </button>
                          <span className="text-xs text-zinc-500">
                            Leave a field blank and save to clear it.
                          </span>
                        </div>
                      </>
                    ) : (
                      <div className="mt-2 space-y-1 text-xs text-zinc-600">
                        {item.owner ? <p>Owner: {item.owner}</p> : null}
                        {item.due_date ? <p>Due: {item.due_date}</p> : null}
                        {item.priority ? <p>Priority: {item.priority}</p> : null}
                      </div>
                    )}
                    {tracked ? (
                      <div className="mt-3 border-t border-zinc-200 pt-2">
                        <button
                          aria-controls={`action-item-history-${tracked.id}`}
                          aria-expanded={
                            historyStates[tracked.id]?.open ?? false
                          }
                          className="text-xs font-medium text-zinc-700 underline decoration-zinc-400 underline-offset-2"
                          disabled={updatingId === tracked.id}
                          onClick={() => toggleHistory(tracked)}
                          type="button"
                        >
                          {historyStates[tracked.id]?.open
                            ? "Hide history"
                            : "History"}
                        </button>
                        {historyStates[tracked.id]?.open ? (
                          <div
                            className="mt-2 rounded-md border border-zinc-200 bg-white p-3"
                            id={`action-item-history-${tracked.id}`}
                          >
                            {(() => {
                              const historyState = historyStates[tracked.id];
                              const state = getActionItemHistoryState(
                                historyState.loading,
                                historyState.error,
                                historyState.records,
                              );
                              if (state === "loading") {
                                return (
                                  <p
                                    className="text-xs text-zinc-600"
                                    role="status"
                                  >
                                    Loading history...
                                  </p>
                                );
                              }
                              if (state === "error") {
                                return (
                                  <div className="text-xs text-amber-900">
                                    <p role="alert">{historyState.error}</p>
                                    <button
                                      className="mt-1 font-medium underline"
                                      onClick={() => void loadHistory(tracked)}
                                      type="button"
                                    >
                                      Retry
                                    </button>
                                  </div>
                                );
                              }
                              if (state === "empty") {
                                return (
                                  <p className="text-xs text-zinc-600">
                                    No change history yet.
                                  </p>
                                );
                              }
                              return (
                                <div>
                                  {historyState.accountabilitySignals.length > 0 ? (
                                    <ul
                                      aria-label="Action-item accountability signals"
                                      className="mb-3 flex flex-wrap gap-1.5"
                                    >
                                      {historyState.accountabilitySignals.map(
                                        (signal) => (
                                          <li
                                            className="rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-xs font-medium text-violet-900"
                                            key={signal}
                                          >
                                            {getMeetingActionItemAccountabilitySignalLabel(signal)}
                                          </li>
                                        ),
                                      )}
                                    </ul>
                                  ) : null}
                                  {historyState.needsReview ? (
                                    <ActionItemSignalReviewButton
                                      actionItemId={tracked.id}
                                      actionItemText={tracked.text}
                                      key={
                                        historyState.records[0]?.changed_at ??
                                        "action-item-review"
                                      }
                                      meetingId={meetingId}
                                    />
                                  ) : null}
                                  <ul className="space-y-2">
                                    {historyState.records.map((record) => (
                                      <li
                                        className="text-xs text-zinc-700"
                                        key={record.id}
                                      >
                                        <p>
                                          <span className="font-medium">
                                            {getActionItemHistoryFieldLabel(
                                              record.field_changed,
                                            )}
                                          </span>
                                          {": "}
                                          {getActionItemHistoryValue(
                                            record.previous_value,
                                          )}
                                          {" → "}
                                          {getActionItemHistoryValue(
                                            record.new_value,
                                          )}
                                        </p>
                                        <time
                                          className="text-zinc-500"
                                          dateTime={record.changed_at}
                                        >
                                          {getActionItemHistoryTimestamp(
                                            record.changed_at,
                                          )}
                                        </time>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              );
                            })()}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                    {overdue ? (
                      <span className="mt-2 inline-flex rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-xs font-semibold text-red-800">
                        Overdue
                      </span>
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
          )}
        </>
      )}
    </section>
  );
}
