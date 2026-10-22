"use client";

import { useState } from "react";

import { createClient } from "@/lib/supabase/client";

type GenerateInsightsButtonProps = {
  meetingId: string;
  disabled?: boolean;
};

export function GenerateInsightsButton({
  meetingId,
  disabled = false,
}: GenerateInsightsButtonProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    setLoading(true);
    setError(null);

    try {
      const supabase = createClient();

      const {
        data: { session },
      } = await supabase.auth.getSession();

      if (!session?.access_token) {
        throw new Error("Your session has expired. Please sign in again.");
      }

      const response = await fetch(
        `http://127.0.0.1:8000/api/meetings/${meetingId}/insights`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${session.access_token}`,
          },
        },
      );

      if (!response.ok) {
        throw new Error("Unable to generate meeting intelligence.");
      }

      window.location.reload();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to generate meeting intelligence.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <button
        type="button"
        disabled={disabled || loading}
        onClick={handleGenerate}
        className="rounded-md bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {loading ? "Generating..." : "Generate Intelligence"}
      </button>

      {error ? (
        <p className="max-w-xs text-right text-sm text-red-700" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}