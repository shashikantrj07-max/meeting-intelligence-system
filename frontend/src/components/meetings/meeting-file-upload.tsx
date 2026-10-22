"use client";

import { useRouter } from "next/navigation";
import { useState, type ChangeEvent } from "react";

import { createClient } from "@/lib/supabase/client";

const MAX_MEETING_FILE_SIZE = 500 * 1024 * 1024;

type SupabaseBrowserClient = ReturnType<typeof createClient>;

async function cleanUpFailedUpload(
  supabase: SupabaseBrowserClient,
  storagePath: string,
  metadataId: string,
): Promise<boolean> {
  let cleanupSucceeded = true;

  try {
    const { error } = await supabase.storage
      .from("meeting-files")
      .remove([storagePath]);
    if (error) {
      cleanupSucceeded = false;
      if (process.env.NODE_ENV === "development") {
        console.error("Unable to clean up failed meeting file upload:", error);
      }
    }
  } catch (error) {
    cleanupSucceeded = false;
    if (process.env.NODE_ENV === "development") {
      console.error("Unexpected meeting file cleanup error:", error);
    }
  }

  try {
    const { error } = await supabase
      .schema("public")
      .from("meeting_files")
      .delete()
      .eq("id", metadataId);
    if (error) {
      cleanupSucceeded = false;
      if (process.env.NODE_ENV === "development") {
        console.error("Unable to clean up meeting file metadata:", error);
      }
    }
  } catch (error) {
    cleanupSucceeded = false;
    if (process.env.NODE_ENV === "development") {
      console.error("Unexpected meeting file metadata cleanup error:", error);
    }
  }

  return cleanupSucceeded;
}

export function MeetingFileUpload({ meetingId }: { meetingId: string }) {
  const router = useRouter();
  const [isUploading, setIsUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    setErrorMessage("");

    if (!file) {
      return;
    }

    if (!file.type.startsWith("audio/") && !file.type.startsWith("video/")) {
      setErrorMessage("Choose an audio or video file.");
      input.value = "";
      return;
    }

    if (file.size <= 0) {
      setErrorMessage("The selected file is empty.");
      input.value = "";
      return;
    }

    if (file.size > MAX_MEETING_FILE_SIZE) {
      setErrorMessage("The file must be 500 MiB or smaller.");
      input.value = "";
      return;
    }

    setIsUploading(true);
    const supabase = createClient();
    const safeFilename = file.name.replace(/[^A-Za-z0-9._-]/g, "_");
    const storagePath = `${meetingId}/${crypto.randomUUID()}-${safeFilename}`;
    let metadataId: string | null = null;

    try {
      const { data: metadata, error: metadataError } = await supabase
        .schema("public")
        .from("meeting_files")
        .insert({
          meeting_id: meetingId,
          storage_path: storagePath,
          original_filename: file.name,
          mime_type: file.type,
          file_size_bytes: file.size,
        })
        .select("id")
        .single();

      if (metadataError || !metadata) {
        if (process.env.NODE_ENV === "development" && metadataError) {
          console.error("Unable to create meeting file metadata:", metadataError);
        }
        setErrorMessage("Unable to prepare the file upload. Please try again.");
        return;
      }

      const currentMetadataId = metadata.id;
      metadataId = currentMetadataId;
      const { error: uploadError } = await supabase.storage
        .from("meeting-files")
        .upload(storagePath, file, {
          contentType: file.type,
          upsert: false,
        });

      if (uploadError) {
        if (process.env.NODE_ENV === "development") {
          console.error("Unable to upload meeting file:", uploadError);
        }
        const cleanupSucceeded = await cleanUpFailedUpload(
          supabase,
          storagePath,
          currentMetadataId,
        );
        metadataId = null;
        setErrorMessage(
          cleanupSucceeded
            ? "Unable to upload the file. Please try again."
            : "The upload failed and cleanup was incomplete. Please refresh and check the Files section before retrying.",
        );
        return;
      }

      metadataId = null;
      router.refresh();
    } catch (error) {
      if (process.env.NODE_ENV === "development") {
        console.error("Unexpected meeting file upload error:", error);
      }
      const cleanupSucceeded = metadataId
        ? await cleanUpFailedUpload(supabase, storagePath, metadataId)
        : true;
      metadataId = null;
      setErrorMessage(
        cleanupSucceeded
          ? "Unable to upload the file. Please try again."
          : "The upload failed and cleanup was incomplete. Please refresh and check the Files section before retrying.",
      );
    } finally {
      input.value = "";
      setIsUploading(false);
    }
  }

  return (
    <div className="space-y-2">
      <label
        className="block text-sm font-medium text-zinc-800"
        htmlFor={`meeting-file-${meetingId}`}
      >
        Upload audio or video
      </label>
      <input
        accept="audio/*,video/*"
        className="block w-full text-sm text-zinc-700 file:mr-4 file:rounded-md file:border-0 file:bg-zinc-100 file:px-3 file:py-2 file:text-sm file:font-medium file:text-zinc-800 hover:file:bg-zinc-200"
        disabled={isUploading}
        id={`meeting-file-${meetingId}`}
        onChange={handleFileChange}
        type="file"
      />
      <p className="text-xs text-zinc-500">
        Audio/video files only; maximum size 500 MiB.
      </p>
      {isUploading ? (
        <p className="text-sm text-blue-700" role="status">
          Uploading file...
        </p>
      ) : null}
      {errorMessage ? (
        <p className="text-sm text-red-800" role="alert">
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
}
