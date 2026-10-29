-- Verifies Phase 9H review against the final Phase 9F–9J schema, including
-- the three-argument accountability RPC introduced by Phase 9J.
-- Run only after all required Phase 9F–9J migrations have been applied.
-- psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--   -f database/tests/verify_phase9h_action_item_signal_review.sql

do $$
begin
  if pg_catalog.to_regclass(
    'public.meeting_action_item_signal_reviews'
  ) is null then
    raise exception 'Missing action-item signal review table';
  end if;

  if not (
    select relrowsecurity
    from pg_catalog.pg_class
    where oid = pg_catalog.to_regclass(
      'public.meeting_action_item_signal_reviews'
    )
  ) then
    raise exception 'RLS is not enabled on the action-item signal review table';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename = 'meeting_action_item_signal_reviews'
      and policyname = 'meeting_action_item_signal_reviews_select_own'
      and roles = array['authenticated']::name[]
      and cmd = 'SELECT'
      and qual like '%meetings%'
      and qual like '%auth.uid()%'
  ) then
    raise exception 'Missing authenticated meeting-owner review policy';
  end if;

  if pg_catalog.has_table_privilege(
    'anon',
    'public.meeting_action_item_signal_reviews',
    'SELECT'
  ) or pg_catalog.has_table_privilege(
    'authenticated',
    'public.meeting_action_item_signal_reviews',
    'INSERT'
  ) or pg_catalog.has_table_privilege(
    'authenticated',
    'public.meeting_action_item_signal_reviews',
    'UPDATE'
  ) or pg_catalog.has_table_privilege(
    'authenticated',
    'public.meeting_action_item_signal_reviews',
    'DELETE'
  ) then
    raise exception 'Review table grants allow unauthorized access or writes';
  end if;

  if not pg_catalog.has_table_privilege(
    'authenticated',
    'public.meeting_action_item_signal_reviews',
    'SELECT'
  ) then
    raise exception 'authenticated is missing review table SELECT access';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc
    where oid =
      'public.get_my_action_item_signal_review_state(uuid)'::regprocedure
      and not prosecdef
      and pg_catalog.has_function_privilege(
        'authenticated',
        'public.get_my_action_item_signal_review_state(uuid)',
        'EXECUTE'
      )
      and not pg_catalog.has_function_privilege(
        'anon',
        'public.get_my_action_item_signal_review_state(uuid)',
        'EXECUTE'
      )
  ) then
    raise exception 'Signal review state RPC privileges are invalid';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc
    where oid =
      'public.review_my_action_item_signals(uuid, uuid)'::regprocedure
      and prosecdef
      and pg_catalog.has_function_privilege(
        'authenticated',
        'public.review_my_action_item_signals(uuid, uuid)',
        'EXECUTE'
      )
      and not pg_catalog.has_function_privilege(
        'anon',
        'public.review_my_action_item_signals(uuid, uuid)',
        'EXECUTE'
      )
  ) then
    raise exception 'Signal review RPC privileges are invalid';
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
    raise exception 'Accountability listing RPC privileges are invalid';
  end if;

  raise notice 'Phase 9H action-item signal review verification passed.';
end;
$$;
