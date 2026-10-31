"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createClient } from "@/lib/supabase/client";

const API_BASE_URL = "http://127.0.0.1:8000";

export function MeetingFileTranscribeButton({
  meetingId,
  fileId,
}: {
  meetingId: string;
  fileId: string;
}) {
  const router = useRouter();
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  async function handleTranscribe() {
    setIsTranscribing(true);
    setErrorMessage("");

    try {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();

      if (!session?.access_token) {
        setErrorMessage("Your session has expired. Please sign in again.");
        return;
      }

      const response = await fetch(
        `${API_BASE_URL}/api/meetings/${meetingId}/files/${fileId}/transcribe`,
        {
          method: "POST",
          headers: {
            "Idempotency-Key": crypto.randomUUID(),
            Authorization: `Bearer ${session.access_token}`,
          },
        },
      );

      if (!response.ok) {
        let message = "Unable to start transcription.";

        try {
          const body = await response.json();

          if (typeof body?.detail === "string") {
            message = body.detail;
          }
        } catch {
          // Keep the generic error when the response is not JSON.
        }

        setErrorMessage(message);
        return;
      }

      router.refresh();
    } catch (error) {
      if (process.env.NODE_ENV === "development") {
        console.error("Unexpected transcription request error:", error);
      }

      setErrorMessage("Unable to start transcription. Please try again.");
    } finally {
      setIsTranscribing(false);
    }
  }

  return (
    <div>
      <button
        className="rounded-md border border-blue-300 px-3 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-60"
        disabled={isTranscribing}
        onClick={handleTranscribe}
        type="button"
      >
        {isTranscribing ? "Transcribing..." : "Transcribe"}
      </button>

      {errorMessage ? (
        <p className="mt-2 text-sm text-red-800" role="alert">
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
}