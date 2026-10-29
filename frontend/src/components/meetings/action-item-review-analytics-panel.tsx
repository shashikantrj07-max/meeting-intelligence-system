"use client";

import Link from "next/link";
import { useState } from "react";

import {
  getActionItemReviewAnalyticsMetrics,
  getActionItemReviewAnalyticsState,
  type MeetingActionItemReviewAnalytics,
} from "@/lib/meeting-action-items-shared";
import {
  buildActionItemAccountabilityHref,
  getActionItemReviewStateForMetric,
  isActionItemReviewMetricSelected,
  type ActionItemAccountabilityFilter,
  type ActionItemReviewStateFilter,
} from "@/lib/dashboard-accountability";
import { getActionItemReviewAnalytics } from "@/lib/meeting-action-items";
import type { DashboardFilters } from "@/lib/dashboard-meetings";

type ActionItemReviewAnalyticsPanelProps = {
  initialAnalytics: MeetingActionItemReviewAnalytics | null;
  initialError: string | null;
  filters: DashboardFilters;
  accountabilityFilter: ActionItemAccountabilityFilter | null;
  selectedReviewState: ActionItemReviewStateFilter | null;
};

export function ActionItemReviewAnalyticsPanel({
  initialAnalytics,
  initialError,
  filters,
  accountabilityFilter,
  selectedReviewState,
}: ActionItemReviewAnalyticsPanelProps) {
  const [analytics, setAnalytics] = useState(initialAnalytics);
  const [error, setError] = useState(initialError);
  const [loading, setLoading] = useState(false);
  const state = getActionItemReviewAnalyticsState(
    loading && !analytics,
    error && !analytics ? error : null,
    analytics,
  );

  async function retry() {
    setLoading(true);
    setError(null);
    try {
      setAnalytics(await getActionItemReviewAnalytics());
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Unable to load action-item review analytics.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section
      aria-label="Action-item review analytics"
      className="mt-4 rounded-lg border border-zinc-200 bg-white p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-zinc-900">
          Review analytics
        </h3>
        {analytics ? (
          <button
            className="text-xs font-medium text-blue-700 underline-offset-2 hover:underline disabled:opacity-50"
            disabled={loading}
            onClick={() => void retry()}
            type="button"
          >
            {loading ? "Refreshing..." : "Refresh"}
          </button>
        ) : null}
      </div>

      {state === "loading" ? (
        <p className="mt-2 text-sm text-zinc-600" role="status">
          Loading review analytics...
        </p>
      ) : state === "error" ? (
        <div className="mt-2 text-sm text-amber-900">
          <p role="alert">
            Review analytics could not be loaded. {error}
          </p>
          <button
            className="mt-1 font-medium underline disabled:opacity-50"
            disabled={loading}
            onClick={() => void retry()}
            type="button"
          >
            {loading ? "Retrying..." : "Retry"}
          </button>
        </div>
      ) : state === "empty" ? (
        <p className="mt-2 text-sm text-zinc-600" role="status">
          Review analytics are not available.
        </p>
      ) : analytics ? (
        <>
          {error ? (
            <p className="mt-2 text-xs text-amber-900" role="alert">
              Could not refresh review analytics. {error}
            </p>
          ) : null}
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {getActionItemReviewAnalyticsMetrics(analytics).map((metric) => {
              const reviewState =
                metric.key === "review_coverage_percent"
                  ? null
                  : getActionItemReviewStateForMetric(metric.key);
              const isCountMetric = reviewState !== null;
              const selected = isActionItemReviewMetricSelected(
                metric.key,
                selectedReviewState,
              );
              const content = (
                <>
                  <span className="block text-xs font-medium">
                    {metric.label}
                  </span>
                  <span className="mt-0.5 block text-xl font-semibold text-zinc-950">
                    {metric.value}
                  </span>
                  <span className="mt-0.5 block text-xs leading-4 text-zinc-500">
                    {metric.description}
                  </span>
                </>
              );

              return (
                <div
                  className={`rounded-md p-2 ${
                    selected
                      ? "bg-blue-50 ring-2 ring-blue-600"
                      : isCountMetric
                        ? "hover:bg-zinc-50"
                        : ""
                  }`}
                  key={metric.key}
                >
                  {reviewState ? (
                    <Link
                      aria-current={selected ? "page" : undefined}
                      aria-label={`Show ${metric.label.toLowerCase()} action items`}
                      className="block rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
                      href={buildActionItemAccountabilityHref(
                        filters,
                        accountabilityFilter ?? "all",
                        1,
                        reviewState,
                      )}
                    >
                      {content}
                    </Link>
                  ) : (
                    <div>{content}</div>
                  )}
                </div>
              );
            })}
          </div>
          <div
            aria-label="Review coverage"
            aria-valuemax={100}
            aria-valuemin={0}
            aria-valuenow={analytics.review_coverage_percent}
            className="mt-3 h-2 overflow-hidden rounded-full bg-zinc-100"
            role="progressbar"
          >
            <div
              className="h-full rounded-full bg-emerald-600 transition-[width]"
              style={{ width: `${analytics.review_coverage_percent}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-zinc-500">
            Reviewed means acknowledged. Needs review means no acknowledgement
            yet or newer meaningful history activity after the last review.
            Reopened since review counts items that became reviewable again
            after a later update; reviewing never changes action-item status.
          </p>
        </>
      ) : null}
    </section>
  );
}
