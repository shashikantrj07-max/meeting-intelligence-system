import { Suspense } from "react";
import Link from "next/link";

import { DeleteMeetingButton } from "@/components/meetings/delete-meeting-button";
import { DeleteTranscriptButton } from "@/components/meetings/delete-transcript-button";
import { MeetingStatusBadge } from "@/components/meetings/meeting-status-badge";
import { formatMeetingDate } from "@/lib/meetings";
import {
  getMeetingById,
  getMeetingInsightsByMeetingId,
  getMeetingProcessingByMeetingId,
  getTranscriptByMeetingId,
} from "@/lib/meetings-server";
import type { Json, MeetingProcessingStage } from "@/types/database";

import { GenerateInsightsButton } from "@/components/meetings/generate-insights-button";

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

  const { data: transcript, error: transcriptError } =
    await getTranscriptByMeetingId(meeting.id);

  if (transcriptError && process.env.NODE_ENV === "development") {
    console.error("Unable to load meeting transcript:", transcriptError);
  }

  const { data: insights, error: insightsError } =
    await getMeetingInsightsByMeetingId(meeting.id);

  if (insightsError && process.env.NODE_ENV === "development") {
    console.error("Unable to load meeting intelligence:", insightsError);
  }

  const { data: processing, error: processingError } =
    await getMeetingProcessingByMeetingId(meeting.id);

  if (processingError && process.env.NODE_ENV === "development") {
    console.error("Unable to load meeting processing status:", processingError);
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

      <section className="mt-6 rounded-xl border border-zinc-200 bg-white p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-zinc-950">Transcript</h2>
            <p className="mt-1 text-sm text-zinc-600">
              Meeting transcript content is private to this meeting.
            </p>
          </div>
          {transcriptError ? (
            <span className="text-sm text-red-800" role="alert">
              Unable to load the transcript.
            </span>
          ) : transcript ? (
            <div className="flex flex-wrap items-center gap-3">
              <Link
                className="rounded-md border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-100"
                href={`/dashboard/meetings/${meeting.id}/transcript`}
              >
                Edit Transcript
              </Link>
              <DeleteTranscriptButton
                meetingId={meeting.id}
                transcriptId={transcript.id}
              />
            </div>
          ) : (
            <Link
              className="rounded-md bg-blue-700 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-800"
              href={`/dashboard/meetings/${meeting.id}/transcript`}
            >
              Add Transcript
            </Link>
          )}
        </div>

        {transcriptError ? (
          <p className="mt-5 rounded-md bg-red-50 p-4 text-sm text-red-800">
            The transcript could not be loaded. Please try again later.
          </p>
        ) : transcript ? (
          <>
            <p className="mt-5 text-xs text-zinc-500">
              Last updated {formatMeetingDate(transcript.updated_at)}
            </p>
            <div className="mt-3 max-h-[36rem] overflow-y-auto rounded-lg bg-zinc-50 p-5">
              <p className="whitespace-pre-wrap break-words text-sm leading-7 text-zinc-800">
                {transcript.content}
              </p>
            </div>
          </>
        ) : (
          <p className="mt-5 rounded-md border border-dashed border-zinc-300 bg-zinc-50 p-5 text-sm text-zinc-600">
            No transcript yet
          </p>
        )}
      </section>

      <section className="mt-6 rounded-xl border border-zinc-200 bg-white p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-zinc-950">
              Meeting Intelligence
            </h2>
            {insights ? (
              <p className="mt-1 text-sm text-zinc-500">
                Last updated {formatMeetingDate(insights.updated_at)}
              </p>
            ) : null}
            <p className="mt-1 text-sm text-zinc-600">
              Generate a summary, decisions, action items, and risks from the transcript.
            </p>
          </div>

          <GenerateInsightsButton
            meetingId={meeting.id}
            hasExistingInsights={Boolean(insights)}
            disabled={!transcript}
          />
        </div>

        {processingError ? (
          <p
            className="mt-5 rounded-md bg-red-50 p-4 text-sm text-red-800"
            role="alert"
          >
            Processing status could not be loaded.
          </p>
        ) : processing ? (
          <ProcessingStatus stage={processing.stage} />
        ) : null}

        {insightsError ? (
          <p
            className="mt-5 rounded-md bg-red-50 p-4 text-sm text-red-800"
            role="alert"
          >
            Meeting intelligence could not be loaded. Please try again later.
          </p>
        ) : insights ? (
          <div className="mt-5 space-y-6">
            <div>
              <h3 className="text-sm font-semibold text-zinc-900">Summary</h3>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-zinc-700">
                {insights.summary}
              </p>
            </div>
            <InsightList
              title="Key Decisions"
              value={insights.key_decisions}
            />
            <InsightList title="Action Items" value={insights.action_items} />
            <InsightList
              title="Risks & Blockers"
              value={insights.risks_blockers}
            />
          </div>
        ) : (
          <p className="mt-5 rounded-md border border-dashed border-zinc-300 bg-zinc-50 p-5 text-sm text-zinc-600">
            No meeting intelligence has been generated yet.
          </p>
        )}
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

function ProcessingStatus({ stage }: { stage: MeetingProcessingStage }) {
  const messages: Record<MeetingProcessingStage, string> = {
    pending: "Meeting processing is queued.",
    transcribing: "The meeting transcript is being processed.",
    analyzing: "Meeting intelligence is being generated.",
    completed: "Meeting processing is complete.",
    failed: "Meeting intelligence generation failed. You can try again.",
  };
  const isFailed = stage === "failed";

  return (
    <p
      className={`mt-5 rounded-md p-4 text-sm ${
        isFailed
          ? "bg-red-50 text-red-800"
          : "bg-blue-50 text-blue-800"
      }`}
      role={isFailed ? "alert" : "status"}
    >
      {messages[stage]}
    </p>
  );
}

function InsightList({
  title,
  value,
}: {
  title: string;
  value: Json;
}) {
  const items = Array.isArray(value) ? value : [];

  return (
    <div>
      <h3 className="text-sm font-semibold text-zinc-900">{title}</h3>

      {items.length === 0 ? (
        <p className="mt-2 text-sm text-zinc-600">None recorded.</p>
      ) : (
        <ul className="mt-2 space-y-3">
          {items.map((item, index) => (
            <li
              className="rounded-lg border border-zinc-200 bg-zinc-50 p-4"
              key={index}
            >
              {typeof item === "object" &&
              item !== null &&
              "text" in item &&
              typeof item.text === "string" ? (
                <>
                  <p className="whitespace-pre-wrap break-words text-sm leading-6 text-zinc-800">
                    {item.text}
                  </p>

                  {"owner" in item &&
                    typeof item.owner === "string" &&
                    item.owner.trim() && (
                      <p className="mt-2 text-xs text-zinc-600">
                        <span className="font-medium text-zinc-700">
                          Owner:
                        </span>{" "}
                        {item.owner}
                      </p>
                    )}

                  {"due_date" in item &&
                    typeof item.due_date === "string" &&
                    item.due_date.trim() && (
                      <p className="mt-1 text-xs text-zinc-600">
                        <span className="font-medium text-zinc-700">
                          Due:
                        </span>{" "}
                        {item.due_date}
                      </p>
                    )}
                </>
              ) : (
                <p className="text-sm text-zinc-600">
                  No readable text is available.
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
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
