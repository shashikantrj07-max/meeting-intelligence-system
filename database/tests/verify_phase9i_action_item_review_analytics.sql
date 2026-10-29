-- Run after applying 20261027000400_phase9i_action_item_review_analytics.sql.
-- psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--   -f database/tests/verify_phase9i_action_item_review_analytics.sql

do $$
begin
  if not exists (
    select 1
    from pg_catalog.pg_proc
    where oid = 'public.get_my_action_item_review_analytics()'::regprocedure
      and not prosecdef
      and pg_catalog.has_function_privilege(
        'authenticated',
        'public.get_my_action_item_review_analytics()',
        'EXECUTE'
      )
      and not pg_catalog.has_function_privilege(
        'anon',
        'public.get_my_action_item_review_analytics()',
        'EXECUTE'
      )
  ) then
    raise exception 'Review analytics RPC privileges are invalid';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc
    where oid = 'public.get_my_action_item_review_analytics()'::regprocedure
      and proconfig @> array['search_path=pg_catalog']
  ) then
    raise exception 'Review analytics RPC search_path is not hardened';
  end if;

  if pg_catalog.has_function_privilege(
    'anon',
    'public.review_my_action_item_signals(uuid, uuid)',
    'EXECUTE'
  ) or pg_catalog.has_table_privilege(
    'authenticated',
    'public.meeting_action_item_signal_reviews',
    'INSERT'
  ) then
    raise exception 'Review analytics migration weakened existing write access';
  end if;

  raise notice 'Phase 9I action-item review analytics verification passed.';
end;
$$;
