create table public.meeting_action_item_history (
  id uuid primary key default gen_random_uuid(),
  action_item_id uuid not null,
  meeting_id uuid not null
    references public.meetings (id) on delete cascade,
  action_item_text text not null,
  field_changed text not null,
  previous_value text,
  new_value text,
  changed_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint meeting_action_item_history_field_valid check (
    field_changed in ('status', 'owner', 'due_date', 'priority')
  )
);

create index meeting_action_item_history_item_changed_idx
  on public.meeting_action_item_history (meeting_id, action_item_id, changed_at desc, id desc);

alter table public.meeting_action_item_history enable row level security;

revoke all on table public.meeting_action_item_history
  from public, anon, authenticated;
grant select on table public.meeting_action_item_history to authenticated;

create policy meeting_action_item_history_select_own
  on public.meeting_action_item_history for select to authenticated
  using (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_action_item_history.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );

create function public.record_meeting_action_item_history()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog
as $$
begin
  if old.status is distinct from new.status then
    insert into public.meeting_action_item_history (
      action_item_id,
      meeting_id,
      action_item_text,
      field_changed,
      previous_value,
      new_value
    ) values (
      old.id,
      old.meeting_id,
      old.text,
      'status',
      old.status,
      new.status
    );
  end if;

  if old.owner is distinct from new.owner then
    insert into public.meeting_action_item_history (
      action_item_id,
      meeting_id,
      action_item_text,
      field_changed,
      previous_value,
      new_value
    ) values (
      old.id,
      old.meeting_id,
      old.text,
      'owner',
      old.owner,
      new.owner
    );
  end if;

  if old.due_date is distinct from new.due_date then
    insert into public.meeting_action_item_history (
      action_item_id,
      meeting_id,
      action_item_text,
      field_changed,
      previous_value,
      new_value
    ) values (
      old.id,
      old.meeting_id,
      old.text,
      'due_date',
      old.due_date,
      new.due_date
    );
  end if;

  if old.priority is distinct from new.priority then
    insert into public.meeting_action_item_history (
      action_item_id,
      meeting_id,
      action_item_text,
      field_changed,
      previous_value,
      new_value
    ) values (
      old.id,
      old.meeting_id,
      old.text,
      'priority',
      old.priority,
      new.priority
    );
  end if;

  return new;
end;
$$;

revoke all on function public.record_meeting_action_item_history()
  from public, anon, authenticated;

create trigger meeting_action_items_record_history
  after update of status, owner, due_date, priority
  on public.meeting_action_items
  for each row
  execute function public.record_meeting_action_item_history();
