"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createClient } from "@/lib/supabase/client";

export function MeetingFileDeleteButton({
  fileId,
  storagePath,
}: {
  fileId: string;
  storagePath: string;
}) {
  const router = useRouter();
  const [isDeleting, setIsDeleting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  async function handleDelete() {
    if (!window.confirm("Delete this meeting file? This action cannot be undone.")) {
      return;
    }

    setIsDeleting(true);
    setErrorMessage("");
    const supabase = createClient();

    try {
      const { error: storageError } = await supabase.storage
        .from("meeting-files")
        .remove([storagePath]);

      if (storageError) {
        if (process.env.NODE_ENV === "development") {
          console.error("Unable to delete meeting file from Storage:", storageError);
        }
        setErrorMessage("Unable to delete the file. Please try again.");
        return;
      }

      const { data, error } = await supabase
        .schema("public")
        .from("meeting_files")
        .delete()
        .eq("id", fileId)
        .select("id")
        .maybeSingle();

      if (error || !data) {
        if (process.env.NODE_ENV === "development" && error) {
          console.error("Unable to delete meeting file metadata:", error);
        }
        setErrorMessage(
          "The file was removed from storage, but its record could not be removed. Please refresh and try again.",
        );
        router.refresh();
        return;
      }

      router.refresh();
    } catch (error) {
      if (process.env.NODE_ENV === "development") {
        console.error("Unexpected meeting file deletion error:", error);
      }
      setErrorMessage("Unable to delete the file. Please try again.");
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <div>
      <button
        className="rounded-md border border-red-300 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
        disabled={isDeleting}
        onClick={handleDelete}
        type="button"
      >
        {isDeleting ? "Deleting..." : "Delete"}
      </button>
      {errorMessage ? (
        <p className="mt-2 text-sm text-red-800" role="alert">
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
}
