-- Run after applying 20261027000100_phase9f_action_item_history.sql.
-- psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--   -f database/tests/verify_phase9f_action_item_history.sql

do $$
begin
  if pg_catalog.to_regclass('public.meeting_action_item_history') is null then
    raise exception 'Missing table public.meeting_action_item_history';
  end if;

  if not (
    select relrowsecurity
    from pg_catalog.pg_class
    where oid = pg_catalog.to_regclass('public.meeting_action_item_history')
  ) then
    raise exception 'RLS is not enabled on public.meeting_action_item_history';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename = 'meeting_action_item_history'
      and policyname = 'meeting_action_item_history_select_own'
      and roles = array['authenticated']::name[]
      and cmd = 'SELECT'
      and qual like '%meetings.owner_id%'
      and qual like '%auth.uid()%'
  ) then
    raise exception 'Missing authenticated meeting-owner history policy';
  end if;

  if pg_catalog.has_table_privilege(
    'anon', 'public.meeting_action_item_history', 'SELECT'
  ) or pg_catalog.has_table_privilege(
    'authenticated', 'public.meeting_action_item_history', 'INSERT'
  ) or pg_catalog.has_table_privilege(
    'authenticated', 'public.meeting_action_item_history', 'UPDATE'
  ) or pg_catalog.has_table_privilege(
    'authenticated', 'public.meeting_action_item_history', 'DELETE'
  ) then
    raise exception 'History table grants permit unauthorized access or writes';
  end if;

  if not pg_catalog.has_table_privilege(
    'authenticated', 'public.meeting_action_item_history', 'SELECT'
  ) then
    raise exception 'authenticated is missing history SELECT access';
  end if;

  if pg_catalog.has_function_privilege(
    'authenticated', 'public.record_meeting_action_item_history()', 'EXECUTE'
  ) or pg_catalog.has_function_privilege(
    'anon', 'public.record_meeting_action_item_history()', 'EXECUTE'
  ) then
    raise exception 'Untrusted roles can execute the history trigger function';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc
    where oid = 'public.record_meeting_action_item_history()'::regprocedure
      and prosecdef
  ) then
    raise exception 'History trigger function is not SECURITY DEFINER';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_trigger
    where tgrelid = 'public.meeting_action_items'::regclass
      and tgname = 'meeting_action_items_record_history'
      and not tgisinternal
  ) then
    raise exception 'Action-item history trigger is missing';
  end if;

  raise notice 'Phase 9F action-item history verification passed.';
end;
$$;
