create or replace function public.get_my_action_item_accountability_items(
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
    status text,
    is_overdue boolean
)
language plpgsql
security invoker
set search_path = pg_catalog
as $$
begin
    if p_status is null
       or p_status not in ('all', 'open', 'in_progress', 'completed', 'overdue')
       or p_offset is null
       or p_offset < 0 then
        raise exception 'Invalid accountability filter or offset.'
            using errcode = '22023';
    end if;

    return query
    select
        mai.id,
        mai.meeting_id,
        m.title,
        mai.text,
        mai.owner,
        mai.due_date,
        mai.status,
        coalesce(
            mai.status <> 'completed'
            and public._try_parse_iso_date(mai.due_date)
                < (current_timestamp at time zone 'utc')::date,
            false
        ) as is_overdue
    from public.meeting_action_items as mai
    join public.meetings as m on m.id = mai.meeting_id
    where m.owner_id = auth.uid()
      and (
          p_status = 'all'
          or mai.status = p_status
          or (
              p_status = 'overdue'
              and mai.status <> 'completed'
              and public._try_parse_iso_date(mai.due_date)
                  < (current_timestamp at time zone 'utc')::date
          )
      )
    order by mai.due_date asc nulls last, mai.created_at desc, mai.id
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
