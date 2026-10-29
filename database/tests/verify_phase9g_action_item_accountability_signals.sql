-- Verifies Phase 9G signals against the final Phase 9F–9J schema, including
-- the three-argument accountability RPC introduced by Phase 9J.
-- Run only after all required Phase 9F–9J migrations have been applied.
-- psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--   -f database/tests/verify_phase9g_action_item_accountability_signals.sql

do $$
begin
  if not exists (
    select 1
    from pg_catalog.pg_proc
    where oid =
      'public.get_my_action_item_accountability_signals(uuid)'::regprocedure
      and not prosecdef
      and pg_catalog.has_function_privilege(
        'authenticated',
        'public.get_my_action_item_accountability_signals(uuid)',
        'EXECUTE'
      )
      and not pg_catalog.has_function_privilege(
        'anon',
        'public.get_my_action_item_accountability_signals(uuid)',
        'EXECUTE'
      )
  ) then
    raise exception 'Action-item signal function privileges are invalid';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc
    where oid =
      'public.get_my_action_item_accountability_items(text, integer, text)'::regprocedure
      and not prosecdef
      and proconfig @> array['search_path=pg_catalog']
      and pg_catalog.has_function_privilege(
        'authenticated',
        'public.get_my_action_item_accountability_items(text, integer, text)',
        'EXECUTE'
      )
      and not pg_catalog.has_function_privilege(
        'anon',
        'public.get_my_action_item_accountability_items(text, integer, text)',
        'EXECUTE'
      )
  ) then
    raise exception 'Accountability items function privileges are invalid';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_trigger
    where tgrelid = 'public.meeting_action_items'::regclass
      and tgname = 'meeting_action_items_record_history'
      and not tgisinternal
  ) then
    raise exception 'Phase 9F history trigger is missing';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename = 'meeting_action_item_history'
      and policyname = 'meeting_action_item_history_select_own'
      and roles = array['authenticated']::name[]
  ) then
    raise exception 'Phase 9F history ownership policy is missing';
  end if;

  raise notice 'Phase 9G action-item accountability verification passed.';
end;
$$;
