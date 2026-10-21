import { Suspense } from "react";
import Link from "next/link";

import { MeetingForm } from "@/components/meetings/meeting-form";
import { getMeetingById } from "@/lib/meetings-server";

export default function EditMeetingPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return (
    <Suspense fallback={<EditMeetingLoading />}>
      <EditMeetingContent params={params} />
    </Suspense>
  );
}

async function EditMeetingContent({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { data: meeting, error } = await getMeetingById(id);

  if (error) {
    if (process.env.NODE_ENV === "development") {
      console.error("Unable to load meeting for editing:", error);
    }

    return (
      <EditMeetingMessage>
        Unable to load this meeting. Please try again later.
      </EditMeetingMessage>
    );
  }

  if (!meeting) {
    return (
      <EditMeetingMessage>
        This meeting was not found or you do not have access to it.
      </EditMeetingMessage>
    );
  }

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-12">
      <Link
        className="text-sm font-medium text-blue-700 hover:text-blue-800"
        href={`/dashboard/meetings/${meeting.id}`}
      >
        ← Back to meeting
      </Link>
      <h1 className="mt-5 text-3xl font-semibold tracking-tight text-zinc-950">
        Edit meeting
      </h1>
      <p className="mt-2 text-zinc-600">
        Update the meeting title, description, date, or duration.
      </p>
      <MeetingForm meeting={meeting} mode="edit" />
    </main>
  );
}

function EditMeetingLoading() {
  return (
    <main
      aria-busy="true"
      className="mx-auto w-full max-w-3xl px-6 py-12 text-sm text-zinc-600"
    >
      Loading meeting...
    </main>
  );
}

function EditMeetingMessage({ children }: { children: string }) {
  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-12">
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
