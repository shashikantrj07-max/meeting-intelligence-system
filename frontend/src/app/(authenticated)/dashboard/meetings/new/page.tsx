import Link from "next/link";

import { MeetingForm } from "@/components/meetings/meeting-form";

export default function NewMeetingPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-12">
      <Link
        className="text-sm font-medium text-blue-700 hover:text-blue-800"
        href="/dashboard"
      >
        ← Back to meetings
      </Link>
      <h1 className="mt-5 text-3xl font-semibold tracking-tight text-zinc-950">
        New meeting
      </h1>
      <p className="mt-2 text-zinc-600">
        Add the basic details for a meeting.
      </p>
      <MeetingForm mode="create" />
    </main>
  );
}
