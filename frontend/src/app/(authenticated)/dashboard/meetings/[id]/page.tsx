import { Suspense } from "react";
import Link from "next/link";

import { DeleteMeetingButton } from "@/components/meetings/delete-meeting-button";
import { MeetingStatusBadge } from "@/components/meetings/meeting-status-badge";
import { formatMeetingDate } from "@/lib/meetings";
import { getMeetingById } from "@/lib/meetings-server";

export default function MeetingDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return (
    <Suspense fallback={<MeetingLoading />}>
      <MeetingDetailContent params={params} />
    </Suspense>
  );
}

async function MeetingDetailContent({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { data: meeting, error } = await getMeetingById(id);

  if (error) {
    if (process.env.NODE_ENV === "development") {
      console.error("Unable to load meeting:", error);
    }

    return (
      <MeetingMessage>
        Unable to load this meeting. Please try again later.
      </MeetingMessage>
    );
  }

  if (!meeting) {
    return (
      <MeetingMessage>
        This meeting was not found or you do not have access to it.
      </MeetingMessage>
    );
  }

  return (
    <main className="mx-auto w-full max-w-4xl px-6 py-12">
      <Link
        className="text-sm font-medium text-blue-700 hover:text-blue-800"
        href="/dashboard"
      >
        ← Back to meetings
      </Link>

      <div className="mt-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-semibold tracking-tight text-zinc-950">
              {meeting.title}
            </h1>
            <MeetingStatusBadge status={meeting.status} />
          </div>
          {meeting.description && (
            <p className="mt-4 whitespace-pre-wrap text-zinc-600">
              {meeting.description}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-3">
          <Link
            className="rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-100"
            href={`/dashboard/meetings/${meeting.id}/edit`}
          >
            Edit Meeting
          </Link>
          <DeleteMeetingButton meetingId={meeting.id} />
        </div>
      </div>

      <section className="mt-8 rounded-xl border border-zinc-200 bg-white p-6">
        <h2 className="text-lg font-semibold text-zinc-950">Meeting details</h2>
        <dl className="mt-5 grid gap-x-8 gap-y-4 sm:grid-cols-2">
          <Detail label="Meeting date">
            {meeting.meeting_date
              ? formatMeetingDate(meeting.meeting_date)
              : "Not set"}
          </Detail>
          <Detail label="Duration">
            {meeting.duration_seconds === null
              ? "Not set"
              : `${meeting.duration_seconds} seconds`}
          </Detail>
          <Detail label="Created">
            {formatMeetingDate(meeting.created_at)}
          </Detail>
          <Detail label="Last updated">
            {formatMeetingDate(meeting.updated_at)}
          </Detail>
        </dl>
      </section>

      <div className="mt-6 grid gap-4 md:grid-cols-3">
        <PlaceholderSection
          description="Meeting participant management will be available in a later phase."
          title="Participants"
        />
        <PlaceholderSection
          description="Meeting file upload and storage will be available in a later phase."
          title="Files"
        />
        <PlaceholderSection
          description="Transcription and processing tools will be available in a later phase."
          title="Processing"
        />
      </div>
    </main>
  );
}

function MeetingLoading() {
  return (
    <main
      aria-busy="true"
      className="mx-auto w-full max-w-4xl px-6 py-12 text-sm text-zinc-600"
    >
      Loading meeting...
    </main>
  );
}

function Detail({ label, children }: { label: string; children: string }) {
  return (
    <div>
      <dt className="text-sm text-zinc-500">{label}</dt>
      <dd className="mt-1 text-sm font-medium text-zinc-900">{children}</dd>
    </div>
  );
}

function PlaceholderSection({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-5">
      <h2 className="font-semibold text-zinc-950">{title}</h2>
      <p className="mt-2 text-sm leading-6 text-zinc-600">{description}</p>
      <span className="mt-4 inline-flex rounded-full bg-zinc-100 px-2.5 py-1 text-xs font-medium text-zinc-600">
        Planned
      </span>
    </section>
  );
}

function MeetingMessage({ children }: { children: string }) {
  return (
    <main className="mx-auto w-full max-w-4xl px-6 py-12">
      <Link
        className="text-sm font-medium text-blue-700 hover:text-blue-800"
        href="/dashboard"
      >
        ← Back to meetings
      </Link>
      <p className="mt-6 rounded-lg border border-zinc-200 bg-white p-5 text-sm text-zinc-700">
        {children}
      </p>
    </main>
  );
}
