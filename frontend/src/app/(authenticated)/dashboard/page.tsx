import { Suspense } from "react";
import Link from "next/link";
import { connection } from "next/server";

import { MeetingStatusBadge } from "@/components/meetings/meeting-status-badge";
import { createClient } from "@/lib/supabase/server";
import { formatMeetingDate } from "@/lib/meetings";

export default function DashboardPage() {
  return (
    <Suspense fallback={<DashboardLoading />}>
      <MeetingsContent />
    </Suspense>
  );
}

async function MeetingsContent() {
  await connection();
  const supabase = await createClient();
  const { data: meetings, error } = await supabase
    .schema("public")
    .from("meetings")
    .select(
      "id, owner_id, title, description, status, meeting_date, duration_seconds, created_at, updated_at",
    )
    .order("created_at", { ascending: false });

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

      {meetings.length === 0 ? (
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
      ) : (
        <ul className="mt-8 grid gap-4 md:grid-cols-2">
          {meetings.map((meeting) => (
            <li key={meeting.id}>
              <Link
                className="group block h-full rounded-xl border border-zinc-200 bg-white p-5 transition hover:border-blue-300 hover:shadow-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
                href={`/dashboard/meetings/${meeting.id}`}
              >
                <div className="flex items-start justify-between gap-4">
                  <h2 className="text-lg font-semibold text-zinc-950 group-hover:text-blue-800">
                    {meeting.title}
                  </h2>
                  <MeetingStatusBadge status={meeting.status} />
                </div>
                {meeting.description && (
                  <p className="mt-3 line-clamp-2 text-sm text-zinc-600">
                    {meeting.description}
                  </p>
                )}
                <dl className="mt-5 grid gap-2 text-xs text-zinc-500">
                  {meeting.meeting_date && (
                    <div className="flex gap-1">
                      <dt>Meeting date:</dt>
                      <dd>{formatMeetingDate(meeting.meeting_date)}</dd>
                    </div>
                  )}
                  <div className="flex gap-1">
                    <dt>Created:</dt>
                    <dd>{formatMeetingDate(meeting.created_at)}</dd>
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
