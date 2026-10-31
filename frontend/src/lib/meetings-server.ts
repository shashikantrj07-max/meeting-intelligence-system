import { connection } from "next/server";

import {
  buildDashboardSearchMeetings,
  buildDashboardMeetings,
  DASHBOARD_MEETING_SEARCH_LIMIT,
  filterDashboardMeetings,
  getDashboardSearchMode,
  toDashboardTitleSearchPattern,
  type DashboardFilters,
} from "@/lib/dashboard-meetings";
import { createClient } from "@/lib/supabase/server";

export async function getDashboardMeetings(filters: DashboardFilters) {
  await connection();
  const supabase = await createClient();
  const searchMode = getDashboardSearchMode(filters.search);

  if (searchMode === "too_short") {
    return { data: [], error: null };
  }

  if (searchMode === "search") {
    const { data: results, error } = await supabase
      .schema("public")
      .rpc("search_my_meetings", {
        p_query: filters.search,
        p_status: filters.status,
        p_limit: DASHBOARD_MEETING_SEARCH_LIMIT,
      });

    if (error) {
      return { data: null, error };
    }

    return {
      data: buildDashboardSearchMeetings(results ?? []),
      error: null,
    };
  }

  const { data: meetings, error } = await supabase
    .schema("public")
    .from("meetings")
    .select(
      "id, title, description, status, meeting_date, created_at, updated_at, meeting_transcripts(meeting_id, updated_at), meeting_insights(meeting_id, updated_at), meeting_processing(meeting_id, stage, updated_at)",
    )
    .ilike("title", toDashboardTitleSearchPattern(filters.search))
    .order("created_at", { ascending: false });

  if (error) {
    return { data: null, error };
  }

  return {
    data: filterDashboardMeetings(
      buildDashboardMeetings(meetings ?? []),
      filters,
    ),
    error: null,
  };
}

export async function getMeetingById(id: string) {
  await connection();
  const supabase = await createClient();

  return supabase
    .schema("public")
    .from("meetings")
    .select(
      "id, owner_id, title, description, status, meeting_date, duration_seconds, created_at, updated_at",
    )
    .eq("id", id)
    .maybeSingle();
}

export async function getTranscriptByMeetingId(meetingId: string) {
  await connection();
  const supabase = await createClient();

  return supabase
    .schema("public")
    .from("meeting_transcripts")
    .select("id, meeting_id, content, created_at, updated_at")
    .eq("meeting_id", meetingId)
    .maybeSingle();
}

export async function getMeetingInsightsByMeetingId(meetingId: string) {
  await connection();
  const supabase = await createClient();

  return supabase
    .schema("public")
    .from("meeting_insights")
    .select(
      "id, meeting_id, summary, key_decisions, action_items, discussion_points, open_questions, next_steps, risks_blockers, created_at, updated_at",
    )
    .eq("meeting_id", meetingId)
    .maybeSingle();
}

export async function getMeetingProcessingByMeetingId(meetingId: string) {
  await connection();
  const supabase = await createClient();

  return supabase
    .schema("public")
    .from("meeting_processing")
    .select(
      "id, meeting_id, stage, error_message, started_at, completed_at, created_at, updated_at",
    )
    .eq("meeting_id", meetingId)
    .maybeSingle();
}

export async function getMeetingFilesByMeetingId(meetingId: string) {
  await connection();
  const supabase = await createClient();

  return supabase
    .schema("public")
    .from("meeting_files")
    .select(
      "id, meeting_id, storage_path, original_filename, mime_type, file_size_bytes, created_at",
    )
    .eq("meeting_id", meetingId)
    .order("created_at", { ascending: false });
}
