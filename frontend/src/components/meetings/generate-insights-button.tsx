"use client";

import { useState } from "react";

import { generateMeetingInsights } from "@/lib/meeting-insights";

type GenerateInsightsButtonProps = {
    meetingId: string;
    hasExistingInsights?: boolean;
    disabled?: boolean;
};

export function GenerateInsightsButton({
    meetingId,
    hasExistingInsights = false,
    disabled = false,
}: GenerateInsightsButtonProps) {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    async function handleGenerate() {
        setLoading(true);
        setError(null);

        try {
            await generateMeetingInsights(meetingId);
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
                {loading
                    ? "Generating..."
                    : hasExistingInsights
                      ? "Regenerate Intelligence"
                      : "Generate Intelligence"}
            </button>

            {error ? (
                <p className="max-w-xs text-right text-sm text-red-700" role="alert">
                    {error}
                </p>
            ) : null}
        </div>
    );
}