"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { GenerateInsightsButton } from "@/components/meetings/generate-insights-button";
import type { MeetingProcessingStage } from "@/types/database";

const PROCESSING_STALE_AFTER_MS = 5 * 60 * 1000;

type MeetingProcessingControlsProps = {
  meetingId: string;
  stage: MeetingProcessingStage | null;
  startedAt: string | null;
  hasExistingInsights: boolean;
  hasTranscript: boolean;
};

export function MeetingProcessingControls({
  meetingId,
  stage,
  startedAt,
  hasExistingInsights,
  hasTranscript,
}: MeetingProcessingControlsProps) {
  const router = useRouter();
  const [staleStartedAt, setStaleStartedAt] = useState<string | null>(null);
  const isStale =
    stage === "analyzing" &&
    startedAt !== null &&
    staleStartedAt === startedAt;
  const isActive =
    stage === "pending" || stage === "transcribing" || stage === "analyzing";

  useEffect(() => {
    if (stage !== "analyzing" || !startedAt) {
      return;
    }

    const startedAtTime = Date.parse(startedAt);
    if (!Number.isFinite(startedAtTime)) {
      return;
    }

    const timeUntilStale =
      startedAtTime + PROCESSING_STALE_AFTER_MS - Date.now();
    const timeoutId = window.setTimeout(
      () => setStaleStartedAt(startedAt),
      Math.max(timeUntilStale, 0),
    );
    return () => window.clearTimeout(timeoutId);
  }, [stage, startedAt]);

  useEffect(() => {
    if (!isActive || isStale) {
      return;
    }

    const intervalId = window.setInterval(() => {
      router.refresh();
    }, 2000);
    return () => window.clearInterval(intervalId);
  }, [isActive, isStale, router]);

  const canRetry = isStale || stage === "failed";
  const statusMessage = isStale
    ? hasExistingInsights
      ? "A newer intelligence generation attempt appears stalled. Your previous intelligence is still available."
      : "This processing attempt appears stalled. You can retry intelligence generation."
    : stage === "pending"
      ? "Meeting processing is queued."
      : stage === "transcribing"
        ? "The meeting transcript is being processed."
        : stage === "analyzing"
          ? "Meeting intelligence is being generated."
          : stage === "completed"
            ? "Meeting processing is complete."
            : stage === "failed"
              ? "Meeting intelligence generation failed. You can try again."
              : null;

  return (
    <div className="flex flex-col items-end gap-2">
      <GenerateInsightsButton
        meetingId={meetingId}
        hasExistingInsights={hasExistingInsights}
        canRetry={canRetry}
        disabled={!hasTranscript || (isActive && !isStale)}
      />
      {statusMessage ? (
        <p
          className={`max-w-xs text-right text-sm ${
            stage === "failed" || isStale ? "text-amber-800" : "text-zinc-600"
          }`}
          role="status"
        >
          {statusMessage}
        </p>
      ) : null}
    </div>
  );
}
