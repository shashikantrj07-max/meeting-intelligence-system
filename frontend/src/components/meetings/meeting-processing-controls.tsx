"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { GenerateInsightsButton } from "@/components/meetings/generate-insights-button";
import { createClient } from "@/lib/supabase/client";
import type { MeetingProcessingStage } from "@/types/database";

const STATUS_POLL_INTERVAL_MS = 2000;

type MeetingProcessingControlsProps = {
  meetingId: string;
  stage: MeetingProcessingStage | null;
  hasExistingInsights: boolean;
  hasTranscript: boolean;
};

export function MeetingProcessingControls({
  meetingId,
  stage,
  hasExistingInsights,
  hasTranscript,
}: MeetingProcessingControlsProps) {
  const router = useRouter();
  const [observedStage, setObservedStage] = useState<MeetingProcessingStage | null>(null);
  const [queuedLocally, setQueuedLocally] = useState(false);
  const displayStage = observedStage ?? (queuedLocally ? "pending" : stage);
  const isActive =
    displayStage === "pending" ||
    displayStage === "transcribing" ||
    displayStage === "analyzing" ||
    displayStage === "retrying";

  useEffect(() => {
    if (!isActive) {
      return;
    }

    let cancelled = false;
    let timeoutId: number | undefined;

    async function pollStatus() {
      try {
        const supabase = createClient();
        const { data, error } = await supabase
          .schema("public")
          .from("meeting_processing")
          .select("stage")
          .eq("meeting_id", meetingId)
          .maybeSingle();

        if (cancelled) return;
        if (!error && data?.stage) {
          const nextStage = data.stage as MeetingProcessingStage;
          setObservedStage(nextStage);
          if (nextStage === "completed" || nextStage === "failed") {
            setQueuedLocally(false);
            router.refresh();
            return;
          }
        }
      } catch {
        // Keep the last known stage and retry on the next polling interval.
      }
      if (!cancelled) {
        timeoutId = window.setTimeout(pollStatus, STATUS_POLL_INTERVAL_MS);
      }
    }

    timeoutId = window.setTimeout(pollStatus, STATUS_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    };
  }, [isActive, meetingId, router]);

  const canRetry = displayStage === "failed";
  const statusMessage = displayStage === "pending"
      ? "Meeting processing is queued."
          : displayStage === "transcribing"
        ? "The meeting transcript is being processed."
          : displayStage === "analyzing"
          ? "Meeting intelligence is being generated."
          : displayStage === "retrying"
            ? "A temporary issue occurred. Processing will retry automatically."
          : displayStage === "completed"
            ? "Meeting processing is complete."
          : displayStage === "failed"
              ? "Meeting intelligence generation failed. You can try again."
              : null;

  return (
    <div className="flex flex-col items-end gap-2">
      <GenerateInsightsButton
        meetingId={meetingId}
        hasExistingInsights={hasExistingInsights}
        canRetry={canRetry}
        disabled={!hasTranscript || isActive}
        onQueued={() => {
          setObservedStage("pending");
          setQueuedLocally(true);
        }}
      />
      {statusMessage ? (
        <p
          className={`max-w-xs text-right text-sm ${
            displayStage === "failed" ? "text-amber-800" : "text-zinc-600"
          }`}
          role="status"
        >
          {statusMessage}
        </p>
      ) : null}
    </div>
  );
}
