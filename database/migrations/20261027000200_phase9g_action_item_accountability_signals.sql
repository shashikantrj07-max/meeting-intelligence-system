create function public.get_my_action_item_accountability_signals(
  p_action_item_id uuid
)
returns table (accountability_signals text[])
language plpgsql
stable
security invoker
set search_path = pg_catalog
as $$
declare
  item_status text;
  history_count bigint;
  has_reopened boolean;
  last_activity_at timestamptz;
begin
  if p_action_item_id is null then
    raise exception 'An action item is required.'
      using errcode = '22023';
  end if;

  select mai.status
  into item_status
  from public.meeting_action_items as mai
  join public.meetings as m on m.id = mai.meeting_id
  where mai.id = p_action_item_id
    and m.owner_id = auth.uid();

  if not found then
    return query select array[]::text[];
    return;
  end if;

  select
    count(*)::bigint,
    coalesce(
      bool_or(
        item_history.field_changed = 'status'
        and item_history.previous_value = 'completed'
        and item_history.new_value in ('open', 'in_progress')
      ),
      false
    ),
    max(item_history.changed_at)
  into history_count, has_reopened, last_activity_at
  from public.meeting_action_item_history as item_history
  where item_history.action_item_id = p_action_item_id;

  return query
  select array_remove(
    array[
      case when has_reopened then 'reopened' end,
      case when history_count >= 2 then 'repeated_updates' end,
      case
        when item_status <> 'completed' and history_count > 0 then 'stale'
      end,
      -- Match the existing seven-day accountability horizon.
      case
        when last_activity_at >= statement_timestamp() - interval '7 days'
          then 'recent_activity'
      end
    ],
    null::text
  );
end;
$$;

revoke all
  on function public.get_my_action_item_accountability_signals(uuid)
  from public, anon;
grant execute
  on function public.get_my_action_item_accountability_signals(uuid)
  to authenticated;

drop function public.get_my_action_item_accountability_items(text, integer);

create function public.get_my_action_item_accountability_items(
  p_status text,
  p_offset integer
)
returns table (
  id uuid,
  meeting_id uuid,
  meeting_title text,
  text text,
  owner text,
  due_date text,
  priority text,
  status text,
  is_overdue boolean,
  attention_reason text,
  follow_up_reason text,
  accountability_signals text[]
)
language plpgsql
security invoker
set search_path = pg_catalog
as $$
declare
  today_utc date := (current_timestamp at time zone 'utc')::date;
begin
  if p_status is null
     or p_status not in (
         'all',
         'open',
         'in_progress',
         'completed',
         'overdue',
         'needs_attention',
         'follow_up',
         'reopened',
         'repeated_updates',
         'stale',
         'recent_activity'
     )
     or p_offset is null
     or p_offset < 0
     or p_offset > 2499975 then
    raise exception 'Invalid accountability filter or offset.'
      using errcode = '22023';
  end if;

  return query
  with classified as (
    select
      mai.id as item_id,
      mai.meeting_id as item_meeting_id,
      m.title as item_meeting_title,
      mai.text as item_text,
      mai.owner as item_owner,
      mai.due_date as item_due_date,
      mai.priority as item_priority,
      mai.status as item_status,
      mai.created_at as item_created_at,
      public._try_parse_iso_date(mai.due_date) as parsed_due_date,
      signal_data.accountability_signals as item_accountability_signals
    from public.meeting_action_items as mai
    join public.meetings as m on m.id = mai.meeting_id
    cross join lateral public.get_my_action_item_accountability_signals(mai.id)
      as signal_data
    where m.owner_id = auth.uid()
  ),
  prioritized as (
    select
      classified.*,
      coalesce(
        item_status <> 'completed'
        and parsed_due_date < today_utc,
        false
      ) as item_is_overdue,
      case
        when item_status = 'completed' then 'completed'
        when parsed_due_date < today_utc then 'overdue'
        when parsed_due_date <= today_utc + 7 then 'due_soon'
        when parsed_due_date is not null then 'due_later'
        else 'no_usable_due_date'
      end as item_attention_reason,
      case
        when item_status = 'completed' then null
        when parsed_due_date < today_utc then 'overdue'
        when parsed_due_date = today_utc then 'due_today'
        when parsed_due_date <= today_utc + 7 then 'due_soon'
        when lower(coalesce(item_priority, '')) in ('urgent', 'high')
          then 'high_priority'
        when parsed_due_date is null then 'missing_due_date'
        else 'due_later'
      end as item_follow_up_reason,
      case
        when item_status = 'completed' then 4
        when parsed_due_date < today_utc then 0
        when parsed_due_date <= today_utc + 7 then 1
        when parsed_due_date is not null then 2
        else 3
      end as urgency_rank,
      case
        when item_status = 'completed' then 6
        when parsed_due_date < today_utc then 0
        when parsed_due_date = today_utc then 1
        when parsed_due_date <= today_utc + 7 then 2
        when lower(coalesce(item_priority, '')) in ('urgent', 'high')
          then 3
        when parsed_due_date is null then 4
        else 5
      end as follow_up_rank,
      case lower(coalesce(item_priority, ''))
        when 'urgent' then 0
        when 'high' then 1
        when 'medium' then 2
        when 'low' then 3
        else 4
      end as priority_rank,
      case item_status
        when 'open' then 0
        when 'in_progress' then 1
        else 2
      end as status_rank
    from classified
  )
  select
    item_id,
    item_meeting_id,
    item_meeting_title,
    item_text,
    item_owner,
    item_due_date,
    item_priority,
    item_status,
    item_is_overdue,
    item_attention_reason,
    item_follow_up_reason,
    item_accountability_signals
  from prioritized
  where p_status = 'all'
     or item_status = p_status
     or (p_status = 'overdue' and item_is_overdue)
     or (p_status = 'needs_attention' and item_status <> 'completed')
     or (p_status = 'follow_up' and item_status <> 'completed')
     or p_status = any(item_accountability_signals)
  order by
    case when p_status = 'follow_up' then follow_up_rank else urgency_rank end,
    case when p_status = 'follow_up' then priority_rank end,
    case when p_status = 'follow_up' then status_rank end,
    case when p_status = 'follow_up' then parsed_due_date end asc nulls last,
    case
      when p_status <> 'follow_up' and urgency_rank in (0, 1, 2)
        then parsed_due_date
    end asc nulls last,
    case when p_status <> 'follow_up' then priority_rank end,
    case when p_status <> 'follow_up' then status_rank end,
    item_created_at desc,
    item_id
  offset p_offset
  limit 26;
end;
$$;

revoke all
  on function public.get_my_action_item_accountability_items(text, integer)
  from public, anon;
grant execute
  on function public.get_my_action_item_accountability_items(text, integer)
  to authenticated;
