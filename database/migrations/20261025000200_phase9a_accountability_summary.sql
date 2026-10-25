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
              and mai.due_date ~ '^\d{4}-\d{2}-\d{2}$'
              and mai.due_date::date < (current_timestamp at time zone 'utc')::date
        )::bigint as overdue
    from public.meeting_action_items mai
    where exists (
        select 1
        from public.meetings m
        where m.id = mai.meeting_id
          and m.owner_id = auth.uid()
    );
$$;

grant execute on function public.get_my_action_item_accountability_summary()
to authenticated;