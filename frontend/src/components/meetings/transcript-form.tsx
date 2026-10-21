"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { createClient } from "@/lib/supabase/client";
import type { Database } from "@/types/database";

type Transcript = Database["public"]["Tables"]["meeting_transcripts"]["Row"];

export function TranscriptForm({
  meetingId,
  transcript,
}: {
  meetingId: string;
  transcript: Transcript | null;
}) {
  const router = useRouter();
  const [content, setContent] = useState(transcript?.content ?? "");
  const [errorMessage, setErrorMessage] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const isEditing = transcript !== null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage("");

    const trimmedContent = content.trim();
    if (!trimmedContent) {
      setErrorMessage("Enter transcript content before saving.");
      return;
    }

    setIsSaving(true);

    try {
      const supabase = createClient();
      const result = isEditing
        ? await supabase
            .schema("public")
            .from("meeting_transcripts")
            .update({ content: trimmedContent })
            .eq("id", transcript.id)
            .eq("meeting_id", meetingId)
            .select("id")
            .maybeSingle()
        : await supabase
            .schema("public")
            .from("meeting_transcripts")
            .insert({ meeting_id: meetingId, content: trimmedContent })
            .select("id")
            .single();

      if (result.error || !result.data) {
        if (process.env.NODE_ENV === "development" && result.error) {
          console.error(
            `Unable to ${isEditing ? "update" : "create"} transcript:`,
            result.error,
          );
        }

        setErrorMessage(
          isEditing
            ? "Unable to update the transcript. Please try again."
            : "Unable to create the transcript. Please try again.",
        );
        return;
      }

      router.push(`/dashboard/meetings/${meetingId}`);
      router.refresh();
    } catch (error) {
      if (process.env.NODE_ENV === "development") {
        console.error("Unexpected transcript save error:", error);
      }
      setErrorMessage(
        isEditing
          ? "Unable to update the transcript. Please try again."
          : "Unable to create the transcript. Please try again.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form
      className="mt-8 space-y-5 rounded-xl border border-zinc-200 bg-white p-6"
      onSubmit={handleSubmit}
    >
      <div>
        <label
          className="block text-sm font-medium text-zinc-800"
          htmlFor="transcript-content"
        >
          Transcript
        </label>
        <textarea
          autoCapitalize="sentences"
          className="mt-2 block min-h-[24rem] w-full resize-y rounded-md border border-zinc-300 px-3 py-3 text-sm leading-6 text-zinc-950 shadow-sm outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
          id="transcript-content"
          onChange={(event) => setContent(event.target.value)}
          placeholder="Paste or type the meeting transcript here..."
          required
          value={content}
        />
      </div>

      {errorMessage && (
        <p
          aria-live="polite"
          className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
          role="alert"
        >
          {errorMessage}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button
          className="rounded-md bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60"
          disabled={isSaving}
          type="submit"
        >
          {isSaving
            ? "Saving..."
            : isEditing
              ? "Save Changes"
              : "Save Transcript"}
        </button>
        <Link
          className="rounded-md px-4 py-2.5 text-sm font-medium text-zinc-700 hover:bg-zinc-100"
          href={`/dashboard/meetings/${meetingId}`}
        >
          Cancel
        </Link>
      </div>
    </form>
  );
}
