-- Phase 4 transcript management.
-- Transcript visibility and mutation inherit ownership from the parent meeting.

create table public.meeting_transcripts (
  id uuid primary key default gen_random_uuid(),
  meeting_id uuid not null unique
    references public.meetings (id) on delete cascade,
  content text not null,
  created_at timestamptz not null default pg_catalog.now(),
  updated_at timestamptz not null default pg_catalog.now(),
  constraint meeting_transcripts_content_not_blank check (
    pg_catalog.btrim(content) <> ''
  )
);

alter table public.meeting_transcripts enable row level security;

revoke all on table public.meeting_transcripts from public, anon, authenticated;
grant select, insert, update, delete
  on table public.meeting_transcripts to authenticated;

create policy meeting_transcripts_select_own
  on public.meeting_transcripts for select to authenticated
  using (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_transcripts.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );

create policy meeting_transcripts_insert_own
  on public.meeting_transcripts for insert to authenticated
  with check (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_transcripts.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );

create policy meeting_transcripts_update_own
  on public.meeting_transcripts for update to authenticated
  using (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_transcripts.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_transcripts.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );

create policy meeting_transcripts_delete_own
  on public.meeting_transcripts for delete to authenticated
  using (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_transcripts.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );

create trigger meeting_transcripts_set_updated_at
  before update on public.meeting_transcripts
  for each row execute function public.set_updated_at();
