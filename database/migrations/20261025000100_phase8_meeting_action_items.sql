-- Phase 8: persist user-owned workflow state separately from generated insights.

create table public.meeting_action_items (
  id uuid primary key default gen_random_uuid(),
  meeting_id uuid not null
    references public.meetings (id) on delete cascade,
  identity_key text not null,
  text text not null,
  owner text,
  due_date text,
  priority text,
  evidence text,
  status text not null default 'open',
  created_at timestamptz not null default pg_catalog.now(),
  updated_at timestamptz not null default pg_catalog.now(),
  constraint meeting_action_items_identity_key_valid check (
    identity_key ~ '^[0-9a-f]{64}$'
  ),
  constraint meeting_action_items_text_not_blank check (
    pg_catalog.btrim(text) <> ''
  ),
  constraint meeting_action_items_status_valid check (
    status in ('open', 'in_progress', 'completed')
  ),
  constraint meeting_action_items_meeting_identity_unique
    unique (meeting_id, identity_key)
);

alter table public.meeting_action_items enable row level security;

revoke all on table public.meeting_action_items from public, anon, authenticated;
grant select, insert, update, delete
  on table public.meeting_action_items to authenticated;

create policy meeting_action_items_select_own
  on public.meeting_action_items for select to authenticated
  using (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_action_items.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );

create policy meeting_action_items_insert_own
  on public.meeting_action_items for insert to authenticated
  with check (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_action_items.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );

create policy meeting_action_items_update_own
  on public.meeting_action_items for update to authenticated
  using (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_action_items.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_action_items.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );

create policy meeting_action_items_delete_own
  on public.meeting_action_items for delete to authenticated
  using (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_action_items.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );

create trigger meeting_action_items_set_updated_at
  before update on public.meeting_action_items
  for each row execute function public.set_updated_at();
