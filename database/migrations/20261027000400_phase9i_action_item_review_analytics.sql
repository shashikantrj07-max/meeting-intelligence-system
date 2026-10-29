create function public.get_my_action_item_review_analytics()
returns table (
  total_reviewable bigint,
  reviewed bigint,
  needs_review bigint,
  reopened_since_review bigint,
  review_coverage_percent numeric
)
language sql
stable
security invoker
set search_path = pg_catalog
as $$
  with current_review_state as (
    select
      signal.accountability_signals,
      review_state.reviewed_at,
      review_state.needs_review as currently_needs_review
    from public.meeting_action_items as mai
    join public.meetings as m on m.id = mai.meeting_id
    cross join lateral public.get_my_action_item_accountability_signals(mai.id)
      as signal
    cross join lateral public.get_my_action_item_signal_review_state(mai.id)
      as review_state
    where m.owner_id = auth.uid()
  ),
  totals as (
    select
      count(*) filter (
        where cardinality(accountability_signals) > 0
      )::bigint as total_reviewable,
      count(*) filter (
        where cardinality(accountability_signals) > 0
          and reviewed_at is not null
          and not currently_needs_review
      )::bigint as reviewed,
      count(*) filter (
        where currently_needs_review
      )::bigint as needs_review,
      count(*) filter (
        where cardinality(accountability_signals) > 0
          and reviewed_at is not null
          and currently_needs_review
      )::bigint as reopened_since_review
    from current_review_state
  )
  select
    total_reviewable,
    reviewed,
    needs_review,
    reopened_since_review,
    coalesce(
      round(
        100.0 * reviewed / nullif(total_reviewable, 0),
        1
      ),
      0::numeric
    ) as review_coverage_percent
  from totals;
$$;

revoke all
  on function public.get_my_action_item_review_analytics()
  from public, anon;
grant execute
  on function public.get_my_action_item_review_analytics()
  to authenticated;
