-- Phase 5 meeting insights.
-- Insight access inherits ownership from the parent meeting.

create table public.meeting_insights (
  id uuid primary key default gen_random_uuid(),
  meeting_id uuid not null unique
    references public.meetings (id) on delete cascade,
  summary text not null,
  key_decisions jsonb not null default '[]'::jsonb,
  action_items jsonb not null default '[]'::jsonb,
  risks_blockers jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default pg_catalog.now(),
  updated_at timestamptz not null default pg_catalog.now(),
  constraint meeting_insights_summary_not_blank check (
    pg_catalog.btrim(summary) <> ''
  )
);

alter table public.meeting_insights enable row level security;

revoke all on table public.meeting_insights from public, anon, authenticated;
grant select, insert, update, delete
  on table public.meeting_insights to authenticated;

create policy meeting_insights_select_own
  on public.meeting_insights for select to authenticated
  using (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_insights.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );

create policy meeting_insights_insert_own
  on public.meeting_insights for insert to authenticated
  with check (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_insights.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );

create policy meeting_insights_update_own
  on public.meeting_insights for update to authenticated
  using (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_insights.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_insights.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );

create policy meeting_insights_delete_own
  on public.meeting_insights for delete to authenticated
  using (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_insights.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );

create trigger meeting_insights_set_updated_at
  before update on public.meeting_insights
  for each row execute function public.set_updated_at();
