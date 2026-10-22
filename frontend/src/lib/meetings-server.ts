import { connection } from "next/server";

import { createClient } from "@/lib/supabase/server";

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
      "id, meeting_id, summary, key_decisions, action_items, risks_blockers, created_at, updated_at",
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
