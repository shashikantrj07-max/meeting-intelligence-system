import { Suspense } from "react";
import Link from "next/link";

import { TranscriptForm } from "@/components/meetings/transcript-form";
import {
  getMeetingById,
  getTranscriptByMeetingId,
} from "@/lib/meetings-server";

export default function MeetingTranscriptPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return (
    <Suspense fallback={<TranscriptLoading />}>
      <MeetingTranscriptContent params={params} />
    </Suspense>
  );
}

async function MeetingTranscriptContent({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { data: meeting, error: meetingError } = await getMeetingById(id);

  if (meetingError) {
    if (process.env.NODE_ENV === "development") {
      console.error("Unable to load meeting for transcript editing:", meetingError);
    }

    return (
      <TranscriptPageMessage>
        Unable to load this meeting. Please try again later.
      </TranscriptPageMessage>
    );
  }

  if (!meeting) {
    return (
      <TranscriptPageMessage>
        This meeting was not found or you do not have access to it.
      </TranscriptPageMessage>
    );
  }

  const { data: transcript, error: transcriptError } =
    await getTranscriptByMeetingId(meeting.id);

  if (transcriptError) {
    if (process.env.NODE_ENV === "development") {
      console.error("Unable to load transcript for editing:", transcriptError);
    }

    return (
      <TranscriptPageMessage>
        Unable to load the transcript. Please try again later.
      </TranscriptPageMessage>
    );
  }

  return (
    <main className="mx-auto w-full max-w-4xl px-6 py-12">
      <Link
        className="text-sm font-medium text-blue-700 hover:text-blue-800"
        href={`/dashboard/meetings/${meeting.id}`}
      >
        ← Back to meeting
      </Link>
      <p className="mt-5 text-sm font-medium text-zinc-500">{meeting.title}</p>
      <h1 className="mt-1 text-3xl font-semibold tracking-tight text-zinc-950">
        {transcript ? "Edit transcript" : "Add transcript"}
      </h1>
      <p className="mt-2 text-zinc-600">
        Transcript text is saved to this meeting. AI analysis is not part of
        this phase.
      </p>
      <TranscriptForm meetingId={meeting.id} transcript={transcript} />
    </main>
  );
}

function TranscriptLoading() {
  return (
    <main
      aria-busy="true"
      className="mx-auto w-full max-w-4xl px-6 py-12 text-sm text-zinc-600"
    >
      Loading transcript...
    </main>
  );
}

function TranscriptPageMessage({ children }: { children: string }) {
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
