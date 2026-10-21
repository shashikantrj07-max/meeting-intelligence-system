"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createClient } from "@/lib/supabase/client";

export function DeleteMeetingButton({ meetingId }: { meetingId: string }) {
  const router = useRouter();
  const [isDeleting, setIsDeleting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  async function handleDelete() {
    if (!window.confirm("Delete this meeting? This action cannot be undone.")) {
      return;
    }

    setIsDeleting(true);
    setErrorMessage("");

    try {
      const { data, error } = await createClient()
        .schema("public")
        .from("meetings")
        .delete()
        .eq("id", meetingId)
        .select("id")
        .maybeSingle();

      if (error || !data) {
        if (process.env.NODE_ENV === "development" && error) {
          console.error("Unable to delete meeting:", error);
        }
        setErrorMessage("Unable to delete the meeting. Please try again.");
        return;
      }

      router.replace("/dashboard");
      router.refresh();
    } catch (error) {
      if (process.env.NODE_ENV === "development") {
        console.error("Unexpected meeting deletion error:", error);
      }
      setErrorMessage("Unable to delete the meeting. Please try again.");
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <div>
      <button
        className="rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
        disabled={isDeleting}
        onClick={handleDelete}
        type="button"
      >
        {isDeleting ? "Deleting..." : "Delete Meeting"}
      </button>
      {errorMessage && (
        <p className="mt-3 text-sm text-red-800" role="alert">
          {errorMessage}
        </p>
      )}
    </div>
  );
}
