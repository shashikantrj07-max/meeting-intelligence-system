"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { createClient } from "@/lib/supabase/client";
import type { Database } from "@/types/database";
import { toDateTimeLocal } from "@/lib/meetings";

type Meeting = Database["public"]["Tables"]["meetings"]["Row"];

export function MeetingForm({
  mode,
  meeting,
}: {
  mode: "create" | "edit";
  meeting?: Meeting;
}) {
  const router = useRouter();
  const [title, setTitle] = useState(meeting?.title ?? "");
  const [description, setDescription] = useState(meeting?.description ?? "");
  const [meetingDate, setMeetingDate] = useState(
    toDateTimeLocal(meeting?.meeting_date ?? null),
  );
  const [duration, setDuration] = useState(
    meeting?.duration_seconds?.toString() ?? "",
  );
  const [errorMessage, setErrorMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage("");

    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      setErrorMessage("Enter a meeting title.");
      return;
    }

    const durationSeconds = duration === "" ? null : Number(duration);
    if (
      durationSeconds !== null &&
      (!Number.isInteger(durationSeconds) || durationSeconds < 0)
    ) {
      setErrorMessage("Duration must be a whole number of zero or more.");
      return;
    }

    setIsSubmitting(true);

    try {
      const supabase = createClient();
      const meetingDateIso = meetingDate
        ? new Date(meetingDate).toISOString()
        : null;

      if (mode === "create") {
        const {
          data: { user },
          error: authError,
        } = await supabase.auth.getUser();

        if (authError || !user) {
          if (process.env.NODE_ENV === "development" && authError) {
            console.error("Unable to verify user before meeting creation:", authError);
          }
          setErrorMessage("Unable to create the meeting. Please sign in again.");
          return;
        }

        const { data, error } = await supabase
          .schema("public")
          .from("meetings")
          .insert({
            owner_id: user.id,
            title: trimmedTitle,
            description: description.trim() || null,
            meeting_date: meetingDateIso,
            duration_seconds: durationSeconds,
          })
          .select("id")
          .single();

        if (error) {
          if (process.env.NODE_ENV === "development") {
            console.error("Unable to create meeting:", error);
          }
          setErrorMessage("Unable to create the meeting. Please try again.");
          return;
        }

        setTitle("");
        setDescription("");
        setMeetingDate("");
        setDuration("");
        router.push(`/dashboard/meetings/${data.id}`);
        router.refresh();
        return;
      }

      if (!meeting) {
        setErrorMessage("Unable to update the meeting. Please try again.");
        return;
      }

      const { data, error } = await supabase
        .schema("public")
        .from("meetings")
        .update({
          title: trimmedTitle,
          description: description.trim() || null,
          meeting_date: meetingDateIso,
          duration_seconds: durationSeconds,
        })
        .eq("id", meeting.id)
        .select("id")
        .maybeSingle();

      if (error || !data) {
        if (process.env.NODE_ENV === "development" && error) {
          console.error("Unable to update meeting:", error);
        }
        setErrorMessage("Unable to update the meeting. Please try again.");
        return;
      }

      setTitle(trimmedTitle);
      setDescription(description.trim());
      setMeetingDate(toDateTimeLocal(meetingDateIso));
      setDuration(durationSeconds?.toString() ?? "");
      router.push(`/dashboard/meetings/${data.id}`);
      router.refresh();
    } catch (error) {
      if (process.env.NODE_ENV === "development") {
        console.error(`Unexpected meeting ${mode} error:`, error);
      }
      setErrorMessage(
        mode === "create"
          ? "Unable to create the meeting. Please try again."
          : "Unable to update the meeting. Please try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  const cancelHref = meeting
    ? `/dashboard/meetings/${meeting.id}`
    : "/dashboard";

  return (
    <form
      className="mt-8 space-y-6 rounded-xl border border-zinc-200 bg-white p-6"
      onSubmit={handleSubmit}
    >
      <div>
        <label
          className="block text-sm font-medium text-zinc-800"
          htmlFor="meeting-title"
        >
          Title <span aria-hidden="true">*</span>
        </label>
        <input
          autoComplete="off"
          className="mt-2 block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm text-zinc-950 shadow-sm outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
          id="meeting-title"
          maxLength={200}
          onChange={(event) => setTitle(event.target.value)}
          required
          value={title}
        />
      </div>

      <div>
        <label
          className="block text-sm font-medium text-zinc-800"
          htmlFor="meeting-description"
        >
          Description
        </label>
        <textarea
          className="mt-2 block min-h-28 w-full rounded-md border border-zinc-300 px-3 py-2 text-sm text-zinc-950 shadow-sm outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
          id="meeting-description"
          maxLength={10_000}
          onChange={(event) => setDescription(event.target.value)}
          value={description}
        />
      </div>

      <div className="grid gap-6 sm:grid-cols-2">
        <div>
          <label
            className="block text-sm font-medium text-zinc-800"
            htmlFor="meeting-date"
          >
            Meeting date
          </label>
          <input
            className="mt-2 block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm text-zinc-950 shadow-sm outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
            id="meeting-date"
            onChange={(event) => setMeetingDate(event.target.value)}
            type="datetime-local"
            value={meetingDate}
          />
        </div>
        <div>
          <label
            className="block text-sm font-medium text-zinc-800"
            htmlFor="meeting-duration"
          >
            Duration (seconds)
          </label>
          <input
            className="mt-2 block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm text-zinc-950 shadow-sm outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
            id="meeting-duration"
            min="0"
            onChange={(event) => setDuration(event.target.value)}
            step="1"
            type="number"
            value={duration}
          />
        </div>
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
          disabled={isSubmitting}
          type="submit"
        >
          {isSubmitting
            ? mode === "create"
              ? "Creating..."
              : "Saving..."
            : mode === "create"
              ? "Create Meeting"
              : "Save Changes"}
        </button>
        <Link
          className="rounded-md px-4 py-2.5 text-sm font-medium text-zinc-700 hover:bg-zinc-100"
          href={cancelHref}
        >
          Cancel
        </Link>
      </div>
    </form>
  );
}
