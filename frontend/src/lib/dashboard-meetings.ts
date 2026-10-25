import type {
  Database,
  MeetingProcessingStage,
} from "@/types/database";

type MeetingRow = Pick<
  Database["public"]["Tables"]["meetings"]["Row"],
  | "id"
  | "title"
  | "description"
  | "status"
  | "meeting_date"
  | "created_at"
  | "updated_at"
>;

type UpdatedMeetingReference = {
  meeting_id: string;
  updated_at: string;
};

type ProcessingReference = UpdatedMeetingReference & {
  stage: MeetingProcessingStage;
};

export type DashboardMeetingQueryRow = MeetingRow & {
  meeting_transcripts:
    | UpdatedMeetingReference
    | UpdatedMeetingReference[]
    | null;
  meeting_insights: UpdatedMeetingReference | UpdatedMeetingReference[] | null;
  meeting_processing:
    | ProcessingReference
    | ProcessingReference[]
    | null;
};

export type DashboardStatusFilter =
  | "all"
  | "processing"
  | "completed"
  | "failed";

export type DashboardFilters = {
  search: string;
  status: DashboardStatusFilter;
};

export type DashboardMeeting = MeetingRow & {
  hasTranscript: boolean;
  hasIntelligence: boolean;
  processingStage: MeetingProcessingStage | null;
  lastUpdated: string;
};

export function toDashboardTitleSearchPattern(search: string): string {
  const escapedSearch = search.replace(/[\\%_]/g, "\\$&");
  return `%${escapedSearch}%`;
}

export function parseDashboardFilters(params: {
  q?: string | string[];
  status?: string | string[];
}): DashboardFilters {
  const search = typeof params.q === "string" ? params.q.trim().slice(0, 200) : "";
  const requestedStatus =
    typeof params.status === "string" ? params.status : "all";
  const status: DashboardStatusFilter =
    requestedStatus === "processing" ||
    requestedStatus === "completed" ||
    requestedStatus === "failed"
      ? requestedStatus
      : "all";

  return { search, status };
}

export function buildDashboardMeetings(
  meetings: DashboardMeetingQueryRow[],
): DashboardMeeting[] {
  return meetings.map((meeting) => {
    const transcript = firstRelation(meeting.meeting_transcripts);
    const intelligence = firstRelation(meeting.meeting_insights);
    const processingState = firstRelation(meeting.meeting_processing);

    return {
      id: meeting.id,
      title: meeting.title,
      description: meeting.description,
      status: meeting.status,
      meeting_date: meeting.meeting_date,
      created_at: meeting.created_at,
      updated_at: meeting.updated_at,
      hasTranscript: transcript !== null,
      hasIntelligence: intelligence !== null,
      processingStage: processingState?.stage ?? null,
      lastUpdated: latestTimestamp(
        meeting.updated_at,
        transcript?.updated_at,
        intelligence?.updated_at,
        processingState?.updated_at,
      ),
    };
  });
}

function firstRelation<T>(value: T | T[] | null): T | null {
  return Array.isArray(value) ? value[0] ?? null : value;
}

function matchesDashboardFilters(
  meeting: Pick<
    DashboardMeeting,
    "title" | "status" | "processingStage"
  >,
  filters: DashboardFilters,
): boolean {
  const search = filters.search.toLocaleLowerCase();
  const matchesSearch =
    search.length === 0 || meeting.title.toLocaleLowerCase().includes(search);
  const matchesStatus = (() => {
    switch (filters.status) {
      case "all":
        return true;
      case "processing":
        return (
          meeting.status === "processing" ||
          isActiveProcessingStage(meeting.processingStage)
        );
      case "completed":
        return (
          meeting.status === "completed" ||
          meeting.processingStage === "completed"
        );
      case "failed":
        return (
          meeting.status === "failed" || meeting.processingStage === "failed"
        );
    }
  })();

  return matchesSearch && matchesStatus;
}

export function filterDashboardMeetings(
  meetings: DashboardMeeting[],
  filters: DashboardFilters,
): DashboardMeeting[] {
  return meetings.filter((meeting) => matchesDashboardFilters(meeting, filters));
}

function latestTimestamp(
  fallback: string,
  ...values: Array<string | undefined>
): string {
  let latest = fallback;
  for (const value of values) {
    if (!value) {
      continue;
    }

    const valueTime = Date.parse(value);
    const latestTime = Date.parse(latest);

    if (Number.isFinite(valueTime) && valueTime > latestTime) {
      latest = value;
    }
  }

  return latest;
}

export function isActiveProcessingStage(
  stage: MeetingProcessingStage | null,
): boolean {
  return (
    stage === "pending" || stage === "transcribing" || stage === "analyzing"
  );
}

export function formatProcessingStage(stage: MeetingProcessingStage): string {
  switch (stage) {
    case "pending":
      return "Queued";
    case "transcribing":
      return "Transcribing";
    case "analyzing":
      return "Analyzing intelligence";
    case "completed":
      return "Completed";
    case "failed":
      return "Failed";
  }
}

export function getProcessingFailureLabel(
  stage: MeetingProcessingStage | null,
  hasTranscript: boolean,
): string | null {
  if (stage !== "failed") {
    return null;
  }

  return hasTranscript ? "Intelligence failed" : "Transcription failed";
}
