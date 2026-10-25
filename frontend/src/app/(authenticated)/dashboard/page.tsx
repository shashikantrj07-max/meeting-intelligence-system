import { Suspense } from "react";
import Link from "next/link";

import { MeetingStatusBadge } from "@/components/meetings/meeting-status-badge";
import { DashboardMeetingFilters } from "@/components/meetings/dashboard-meeting-filters";
import {
  formatProcessingStage,
  getProcessingFailureLabel,
  isActiveProcessingStage,
  parseDashboardFilters,
} from "@/lib/dashboard-meetings";
import {
  buildActionItemMeetingHref,
  buildActionItemAccountabilityHref,
  getActionItemFollowUpReasonLabel,
  parseActionItemAccountabilityFilter,
  parseActionItemsPage,
  type ActionItemAccountabilityFilter,
} from "@/lib/dashboard-accountability";
import {
  getActionItemAccountabilityItems,
  getActionItemAccountabilitySummary,
} from "@/lib/meeting-action-items-server";
import { getDashboardMeetings } from "@/lib/meetings-server";
import { formatMeetingDate } from "@/lib/meetings";

type DashboardSearchParams = {
  q?: string | string[];
  status?: string | string[];
  actionItemStatus?: string | string[];
  actionItemsPage?: string | string[];
};

export default function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<DashboardSearchParams>;
}) {
  return (
    <Suspense fallback={<DashboardLoading />}>
      <DashboardContent searchParams={searchParams} />
    </Suspense>
  );
}

async function DashboardContent({
  searchParams,
}: {
  searchParams: Promise<DashboardSearchParams>;
}) {
  const params = await searchParams;
  const filters = parseDashboardFilters(params);
  const accountabilityFilter = parseActionItemAccountabilityFilter(
    params.actionItemStatus,
  );
  const accountabilityPage = parseActionItemsPage(params.actionItemsPage);
  const [meetingsResult, accountabilityResult, accountabilityItemsResult] =
    await Promise.all([
    getDashboardMeetings(filters),
    getActionItemAccountabilitySummary(),
    accountabilityFilter
      ? getActionItemAccountabilityItems(
          accountabilityFilter,
          accountabilityPage,
        )
      : Promise.resolve({ data: null, error: null }),
  ]);
  if (
    accountabilityResult.error &&
    process.env.NODE_ENV === "development"
  ) {
    console.error(
      "Unable to load action-item accountability:",
      accountabilityResult.error,
    );
  }
  if (
    accountabilityItemsResult.error &&
    process.env.NODE_ENV === "development"
  ) {
    console.error(
      "Unable to load action-item accountability items:",
      accountabilityItemsResult.error,
    );
  }
  const { data: meetings, error } = meetingsResult;
  const hasActiveFilters =
    filters.search.length > 0 || filters.status !== "all";

  if (error) {
    if (process.env.NODE_ENV === "development") {
      console.error("Unable to load meetings:", error);
    }

    return (
      <main className="mx-auto w-full max-w-6xl px-6 py-12">
        <PageHeading />
        <div
          className="mt-8 rounded-lg border border-red-200 bg-red-50 p-5 text-sm text-red-800"
          role="alert"
        >
          Unable to load your meetings. Please try again later.
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-12">
      <PageHeading />

      <DashboardMeetingFilters
        filters={filters}
        hasActiveFilters={hasActiveFilters}
      />
      {accountabilityResult.data ? (
        <section
          aria-label="Action-item accountability"
          className="mt-8"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-zinc-950">
              Action-item accountability
            </h2>
            <Link
              className="text-sm font-semibold text-blue-700 underline-offset-2 hover:underline"
              href={buildActionItemAccountabilityHref(
                filters,
                "needs_attention",
              )}
            >
              View needs attention
            </Link>
            <Link
              className="text-sm font-semibold text-blue-700 underline-offset-2 hover:underline"
              href={buildActionItemAccountabilityHref(filters, "follow_up")}
            >
              View follow-up
            </Link>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <AccountabilityCard
              label="Tracked"
              value={accountabilityResult.data.total}
              filters={filters}
              accountabilityFilter="all"
              selected={accountabilityFilter === "all"}
            />
            <AccountabilityCard
              label="Open"
              value={accountabilityResult.data.open}
              filters={filters}
              accountabilityFilter="open"
              selected={accountabilityFilter === "open"}
            />
            <AccountabilityCard
              label="In Progress"
              value={accountabilityResult.data.in_progress}
              filters={filters}
              accountabilityFilter="in_progress"
              selected={accountabilityFilter === "in_progress"}
            />
            <AccountabilityCard
              label="Completed"
              value={accountabilityResult.data.completed}
              filters={filters}
              accountabilityFilter="completed"
              selected={accountabilityFilter === "completed"}
            />
            <AccountabilityCard
              label="Overdue"
              value={accountabilityResult.data.overdue}
              overdue
              filters={filters}
              accountabilityFilter="overdue"
              selected={accountabilityFilter === "overdue"}
            />
          </div>
        </section>
      ) : (
        <p
          className="mt-6 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
          role="status"
        >
          Action-item accountability counts could not be loaded. Refresh the
          page to retry.
        </p>
      )}

      {accountabilityFilter ? (
        <AccountabilityDrilldown
          filter={accountabilityFilter}
          filters={filters}
          page={accountabilityPage}
          result={accountabilityItemsResult}
        />
      ) : null}

      {meetings.length === 0 && !hasActiveFilters ? (
        <section className="mt-8 rounded-xl border border-dashed border-zinc-300 bg-white px-6 py-14 text-center">
          <h2 className="text-lg font-semibold text-zinc-950">
            No meetings yet
          </h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-zinc-600">
            Create your first meeting to start organizing its details and
            follow-up work.
          </p>
          <Link
            className="mt-6 inline-flex rounded-md bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-800"
            href="/dashboard/meetings/new"
          >
            New Meeting
          </Link>
        </section>
      ) : meetings.length === 0 ? (
        <section className="mt-8 rounded-xl border border-dashed border-zinc-300 bg-white px-6 py-14 text-center">
          <h2 className="text-lg font-semibold text-zinc-950">
            No matching meetings
          </h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-zinc-600">
            Try a different title or status filter.
          </p>
          <Link
            className="mt-5 inline-flex rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-100"
            href="/dashboard"
          >
            Clear search and filters
          </Link>
        </section>
      ) : (
        <ul className="mt-8 grid gap-4 md:grid-cols-2">
          {meetings.map((meeting) => (
            <li key={meeting.id}>
              <Link
                className="group block h-full rounded-xl border border-zinc-200 bg-white p-5 transition hover:border-blue-300 hover:shadow-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
                href={`/dashboard/meetings/${meeting.id}`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <h2 className="break-words text-lg font-semibold text-zinc-950 group-hover:text-blue-800">
                      {meeting.title}
                    </h2>
                    {meeting.description && (
                      <p className="mt-3 line-clamp-2 text-sm text-zinc-600">
                        {meeting.description}
                      </p>
                    )}
                  </div>
                  <MeetingStatusBadge status={meeting.status} />
                </div>
                <ul className="mt-4 flex flex-wrap gap-2 text-xs">
                  <li
                    className={`rounded-full border px-2.5 py-1 ${
                      meeting.hasTranscript
                        ? "border-green-200 bg-green-50 text-green-800"
                        : "border-zinc-200 bg-zinc-50 text-zinc-600"
                    }`}
                  >
                    {meeting.hasTranscript
                      ? "Transcript available"
                      : "No transcript"}
                  </li>
                  <li
                    className={`rounded-full border px-2.5 py-1 ${
                      meeting.hasIntelligence
                        ? "border-green-200 bg-green-50 text-green-800"
                        : "border-zinc-200 bg-zinc-50 text-zinc-600"
                    }`}
                  >
                    {meeting.hasIntelligence
                      ? "Intelligence available"
                      : "No intelligence"}
                  </li>
                  {meeting.processingStage &&
                  isActiveProcessingStage(meeting.processingStage) ? (
                    <li className="rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-blue-800">
                      Processing: {formatProcessingStage(meeting.processingStage)}
                    </li>
                  ) : null}
                  {getProcessingFailureLabel(
                    meeting.processingStage,
                    meeting.hasTranscript,
                  ) ? (
                    <li className="rounded-full border border-red-200 bg-red-50 px-2.5 py-1 text-red-800">
                      {getProcessingFailureLabel(
                        meeting.processingStage,
                        meeting.hasTranscript,
                      )}
                    </li>
                  ) : null}
                </ul>
                <dl className="mt-4 grid gap-2 text-xs text-zinc-500 sm:grid-cols-2">
                  <div className="flex gap-1">
                    <dt>Meeting date:</dt>
                    <dd>
                      {meeting.meeting_date
                        ? formatMeetingDate(meeting.meeting_date)
                        : "Not set"}
                    </dd>
                  </div>
                  <div className="flex gap-1">
                    <dt>Last updated:</dt>
                    <dd>{formatMeetingDate(meeting.lastUpdated)}</dd>
                  </div>
                </dl>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

function AccountabilityCard({
  label,
  value,
  overdue = false,
  filters,
  accountabilityFilter,
  selected,
}: {
  label: string;
  value: number;
  overdue?: boolean;
  filters: ReturnType<typeof parseDashboardFilters>;
  accountabilityFilter: ActionItemAccountabilityFilter;
  selected: boolean;
}) {
  return (
    <Link
      aria-current={selected ? "page" : undefined}
      className={`block rounded-lg border p-4 transition hover:border-blue-400 hover:shadow-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 ${
        overdue
          ? "border-red-200 bg-red-50 text-red-900"
          : "border-zinc-200 bg-white text-zinc-900"
      } ${selected ? "ring-2 ring-blue-600" : ""}`}
      href={buildActionItemAccountabilityHref(filters, accountabilityFilter)}
    >
      <span className="block text-xs font-medium">{label}</span>
      <span className="mt-1 block text-2xl font-semibold">{value}</span>
    </Link>
  );
}

function AccountabilityDrilldown({
  filter,
  filters,
  page,
  result,
}: {
  filter: ActionItemAccountabilityFilter;
  filters: ReturnType<typeof parseDashboardFilters>;
  page: number;
  result: Awaited<ReturnType<typeof getActionItemAccountabilityItems>>;
}) {
  const filterLabels: Record<ActionItemAccountabilityFilter, string> = {
    all: "Tracked",
    open: "Open",
    in_progress: "In Progress",
    completed: "Completed",
    overdue: "Overdue",
    needs_attention: "Needs attention",
    follow_up: "Follow-up",
  };
  const items = result.data?.items ?? [];

  return (
    <section
      aria-label={`${filterLabels[filter]} action items`}
      className="mt-8 rounded-xl border border-zinc-200 bg-white p-5"
    >
      <h2 className="text-lg font-semibold text-zinc-950">
        {filterLabels[filter]} action items
      </h2>
      <nav
        aria-label="Filter accountability items"
        className="mt-3 flex flex-wrap gap-2"
      >
        {(
          [
            "needs_attention",
            "follow_up",
            "overdue",
            "open",
            "in_progress",
            "completed",
            "all",
          ] as const
        ).map((option) => (
          <Link
            aria-current={filter === option ? "page" : undefined}
            className={`rounded-full border px-3 py-1 text-xs font-medium ${
              filter === option
                ? "border-blue-700 bg-blue-50 text-blue-900"
                : "border-zinc-300 text-zinc-700 hover:bg-zinc-50"
            }`}
            href={buildActionItemAccountabilityHref(filters, option)}
            key={option}
          >
            {filterLabels[option]}
          </Link>
        ))}
      </nav>
      {result.error ? (
        <p className="mt-3 text-sm text-red-800" role="alert">
          Action items could not be loaded. Refresh the page to retry.
        </p>
      ) : items.length === 0 ? (
        <p className="mt-3 text-sm text-zinc-600">
          No action items match this filter.
        </p>
      ) : (
        <>
          <ul className="mt-4 divide-y divide-zinc-200">
            {items.map((item) => (
              <li
                className="flex flex-wrap items-start justify-between gap-3 py-4 first:pt-0 last:pb-0"
                key={item.id}
              >
                <div className="min-w-0">
                  <p className="whitespace-pre-wrap break-words text-sm font-medium text-zinc-900">
                    {item.text}
                  </p>
                  <p className="mt-1 text-xs text-zinc-600">
                    <span className="font-medium text-zinc-800">
                      {item.status.replace("_", " ")}
                    </span>
                    {item.owner ? ` · Owner: ${item.owner}` : ""}
                    {item.due_date ? ` · Due: ${item.due_date}` : " · No due date"}
                    {item.priority ? ` · Priority: ${item.priority}` : ""}
                    {item.is_overdue ? (
                      <span className="ml-2 rounded-full border border-red-200 bg-red-50 px-2 py-0.5 font-semibold text-red-800">
                        Overdue
                      </span>
                    ) : item.attention_reason === "due_soon" ? (
                      <span className="ml-2 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 font-semibold text-amber-900">
                        Due soon
                      </span>
                    ) : filter === "needs_attention" ? (
                      <span className="ml-2 text-zinc-500">
                        {item.attention_reason === "due_later"
                          ? "Due later"
                          : "No usable due date"}
                      </span>
                    ) : filter === "follow_up" ? (
                      <span className="ml-2 rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 font-semibold text-blue-900">
                        {getActionItemFollowUpReasonLabel(item.follow_up_reason)}
                      </span>
                    ) : null}
                  </p>
                </div>
                <Link
                  className="shrink-0 text-sm font-medium text-blue-700 underline-offset-2 hover:underline"
                  href={buildActionItemMeetingHref(item.meeting_id)}
                >
                  {item.meeting_title}
                </Link>
              </li>
            ))}
          </ul>
          <nav
            aria-label="Action-item pages"
            className="mt-4 flex items-center justify-between border-t border-zinc-200 pt-4 text-sm"
          >
            {page > 1 ? (
              <Link
                className="font-medium text-blue-700 hover:underline"
                href={buildActionItemAccountabilityHref(
                  filters,
                  filter,
                  page - 1,
                )}
              >
                Previous
              </Link>
            ) : (
              <span />
            )}
            <span className="text-zinc-600">Page {page}</span>
            {result.data?.has_more ? (
              <Link
                className="font-medium text-blue-700 hover:underline"
                href={buildActionItemAccountabilityHref(
                  filters,
                  filter,
                  page + 1,
                )}
              >
                Next
              </Link>
            ) : (
              <span />
            )}
          </nav>
        </>
      )}
    </section>
  );
}

function DashboardLoading() {
  return (
    <main
      aria-busy="true"
      className="mx-auto w-full max-w-6xl px-6 py-12 text-sm text-zinc-600"
    >
      Loading your meetings...
    </main>
  );
}

function PageHeading() {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="text-sm font-semibold tracking-wide text-blue-700">
          WORKSPACE
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-950">
          Meetings
        </h1>
        <p className="mt-2 text-zinc-600">
          Organize your meetings and keep important details in one place.
        </p>
      </div>
      <Link
        className="inline-flex rounded-md bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-800"
        href="/dashboard/meetings/new"
      >
        New Meeting
      </Link>
    </div>
  );
}
