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
import { getDashboardMeetings } from "@/lib/meetings-server";
import { formatMeetingDate } from "@/lib/meetings";

type DashboardSearchParams = {
  q?: string | string[];
  status?: string | string[];
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
  const filters = parseDashboardFilters(await searchParams);
  const { data: meetings, error } = await getDashboardMeetings(filters);
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
