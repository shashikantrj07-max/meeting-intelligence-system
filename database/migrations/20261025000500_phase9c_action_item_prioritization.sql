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
    attention_reason text
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
           'needs_attention'
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
            public._try_parse_iso_date(mai.due_date) as parsed_due_date
        from public.meeting_action_items as mai
        join public.meetings as m on m.id = mai.meeting_id
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
                when item_status = 'completed' then 4
                when parsed_due_date < today_utc then 0
                when parsed_due_date <= today_utc + 7 then 1
                when parsed_due_date is not null then 2
                else 3
            end as urgency_rank,
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
        item_attention_reason
    from prioritized
    where p_status = 'all'
       or item_status = p_status
       or (p_status = 'overdue' and item_is_overdue)
       or (p_status = 'needs_attention' and item_status <> 'completed')
    order by
        urgency_rank,
        case when urgency_rank in (0, 1, 2) then parsed_due_date end asc nulls last,
        priority_rank,
        status_rank,
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
