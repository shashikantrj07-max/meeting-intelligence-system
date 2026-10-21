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
