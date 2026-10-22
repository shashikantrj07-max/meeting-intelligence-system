"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import type { MeetingProcessingStage } from "@/types/database";

type MeetingProcessingStatusRefreshProps = {
  stage: MeetingProcessingStage | null;
};

export function MeetingProcessingStatusRefresh({
  stage,
}: MeetingProcessingStatusRefreshProps) {
  const router = useRouter();

  useEffect(() => {
    if (
      stage !== "pending" &&
      stage !== "transcribing" &&
      stage !== "analyzing"
    ) {
      return;
    }

    const intervalId = window.setInterval(() => {
      router.refresh();
    }, 2000);

    return () => window.clearInterval(intervalId);
  }, [router, stage]);

  return null;
}
