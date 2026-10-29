"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { reviewMeetingActionItemSignals } from "@/lib/meeting-action-items";

type ActionItemSignalReviewButtonProps = {
  meetingId: string;
  actionItemId: string;
  actionItemText: string;
};

export function ActionItemSignalReviewButton({
  meetingId,
  actionItemId,
  actionItemText,
}: ActionItemSignalReviewButtonProps) {
  const router = useRouter();
  const [reviewed, setReviewed] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function markReviewed() {
    setPending(true);
    setError(null);
    setReviewed(true);
    try {
      await reviewMeetingActionItemSignals(meetingId, actionItemId);
      router.refresh();
    } catch (reviewError) {
      setReviewed(false);
      setError(
        reviewError instanceof Error
          ? reviewError.message
          : "Unable to mark action-item signals as reviewed.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mt-2">
      {reviewed ? (
        <p className="text-xs font-medium text-emerald-800" role="status">
          Reviewed
        </p>
      ) : (
        <button
          aria-label={`Mark accountability signals reviewed for ${actionItemText}`}
          className="rounded-md border border-violet-300 bg-white px-2.5 py-1 text-xs font-medium text-violet-900 hover:bg-violet-50 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={pending}
          onClick={() => void markReviewed()}
          type="button"
        >
          {pending ? "Marking reviewed..." : "Mark reviewed"}
        </button>
      )}
      {error ? (
        <p className="mt-1 text-xs text-red-800" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
