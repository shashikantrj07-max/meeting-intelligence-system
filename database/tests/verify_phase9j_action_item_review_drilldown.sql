-- Run after applying 20261027000500_phase9j_action_item_review_drilldown.sql.
-- psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--   -f database/tests/verify_phase9j_action_item_review_drilldown.sql

do $$
begin
  if not exists (
    select 1
    from pg_catalog.pg_proc
    where oid =
      'public.get_my_action_item_accountability_items(text,integer,text)'::regprocedure
      and not prosecdef
      and proargnames[1:3] = array['p_status', 'p_offset', 'p_review_state']
      and pg_catalog.has_function_privilege(
        'authenticated',
        'public.get_my_action_item_accountability_items(text,integer,text)',
        'EXECUTE'
      )
      and not pg_catalog.has_function_privilege(
        'anon',
        'public.get_my_action_item_accountability_items(text,integer,text)',
        'EXECUTE'
      )
  ) then
    raise exception 'Review drilldown RPC security or signature is invalid';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc
    where oid =
      'public.get_my_action_item_accountability_items(text,integer,text)'::regprocedure
      and proconfig @> array['search_path=pg_catalog']
  ) then
    raise exception 'Review drilldown RPC search_path is not hardened';
  end if;

  if pg_catalog.has_table_privilege(
    'authenticated',
    'public.meeting_action_item_signal_reviews',
    'INSERT'
  ) or pg_catalog.has_table_privilege(
    'authenticated',
    'public.meeting_action_item_signal_reviews',
    'UPDATE'
  ) then
    raise exception 'Review drilldown migration weakened direct-write protection';
  end if;

  raise notice 'Phase 9J action-item review drilldown verification passed.';
end;
$$;
