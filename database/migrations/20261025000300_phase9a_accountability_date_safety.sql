create or replace function public._try_parse_iso_date(input_value text)
returns date
language plpgsql
immutable
strict
security invoker
set search_path = pg_catalog
as $$
begin
    if input_value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' then
        return null;
    end if;

    return input_value::date;
exception
    when datetime_field_overflow or invalid_datetime_format then
        return null;
end;
$$;

revoke all on function public._try_parse_iso_date(text) from public, anon;
grant execute on function public._try_parse_iso_date(text) to authenticated;

create or replace function public.get_my_action_item_accountability_summary()
returns table (
    total bigint,
    open bigint,
    in_progress bigint,
    completed bigint,
    overdue bigint
)
language sql
security invoker
set search_path = public
as $$
    select
        count(*)::bigint as total,
        count(*) filter (where mai.status = 'open')::bigint as open,
        count(*) filter (where mai.status = 'in_progress')::bigint as in_progress,
        count(*) filter (where mai.status = 'completed')::bigint as completed,
        count(*) filter (
            where mai.status <> 'completed'
              and public._try_parse_iso_date(mai.due_date)
                  < (current_timestamp at time zone 'utc')::date
        )::bigint as overdue
    from public.meeting_action_items mai
    where exists (
        select 1
        from public.meetings m
        where m.id = mai.meeting_id
          and m.owner_id = auth.uid()
    );
$$;

revoke all
    on function public.get_my_action_item_accountability_summary()
    from public, anon;
grant execute
    on function public.get_my_action_item_accountability_summary()
    to authenticated;
