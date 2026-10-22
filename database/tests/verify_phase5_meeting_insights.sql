-- Run after applying 20261022000100_phase5_meeting_insights.sql.
-- psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--   -f database/tests/verify_phase5_meeting_insights.sql

do $$
declare
  expected_policy text;
  expected_column text;
begin
  if pg_catalog.to_regclass('public.meeting_insights') is null then
    raise exception 'Missing table public.meeting_insights';
  end if;

  if not (
    select relrowsecurity
    from pg_catalog.pg_class
    where oid = pg_catalog.to_regclass('public.meeting_insights')
  ) then
    raise exception 'RLS is not enabled on public.meeting_insights';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_constraint
    where conrelid = pg_catalog.to_regclass('public.meeting_insights')
      and conname = 'meeting_insights_meeting_id_key'
      and contype = 'u'
  ) then
    raise exception 'meeting_insights.meeting_id is not unique';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_constraint
    where conrelid = pg_catalog.to_regclass('public.meeting_insights')
      and conname = 'meeting_insights_meeting_id_fkey'
      and contype = 'f'
      and confrelid = pg_catalog.to_regclass('public.meetings')
      and confdeltype = 'c'
  ) then
    raise exception 'meeting_id foreign key must reference meetings and cascade on delete';
  end if;

  if not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'meeting_insights'
      and column_name = 'summary'
      and data_type = 'text'
      and is_nullable = 'NO'
  ) then
    raise exception 'meeting_insights.summary must be NOT NULL text';
  end if;

  foreach expected_column in array array[
    'key_decisions',
    'action_items',
    'risks_blockers'
  ]
  loop
    if not exists (
      select 1
      from information_schema.columns
      where table_schema = 'public'
        and table_name = 'meeting_insights'
        and column_name = expected_column
        and data_type = 'jsonb'
        and is_nullable = 'NO'
    ) then
      raise exception 'meeting_insights.% must be NOT NULL jsonb', expected_column;
    end if;

    if not exists (
      select 1
      from pg_catalog.pg_attribute as attribute
      join pg_catalog.pg_attrdef as default_value
        on default_value.adrelid = attribute.attrelid
       and default_value.adnum = attribute.attnum
      where attribute.attrelid =
          pg_catalog.to_regclass('public.meeting_insights')
        and attribute.attname = expected_column
        and not attribute.attisdropped
        and pg_catalog.pg_get_expr(
          default_value.adbin, default_value.adrelid
        ) = '''[]''::jsonb'
    ) then
      raise exception 'meeting_insights.% must default to []::jsonb',
        expected_column;
    end if;
  end loop;

  foreach expected_policy in array array[
    'meeting_insights_select_own',
    'meeting_insights_insert_own',
    'meeting_insights_update_own',
    'meeting_insights_delete_own'
  ]
  loop
    if not exists (
      select 1
      from pg_catalog.pg_policies
      where schemaname = 'public'
        and tablename = 'meeting_insights'
        and policyname = expected_policy
        and roles = array['authenticated']::name[]
    ) then
      raise exception 'Missing authenticated ownership policy %',
        expected_policy;
    end if;
  end loop;

  if pg_catalog.has_table_privilege(
    'public', 'public.meeting_insights', 'SELECT'
  ) or pg_catalog.has_table_privilege(
    'public', 'public.meeting_insights', 'INSERT'
  ) or pg_catalog.has_table_privilege(
    'public', 'public.meeting_insights', 'UPDATE'
  ) or pg_catalog.has_table_privilege(
    'public', 'public.meeting_insights', 'DELETE'
  ) or pg_catalog.has_table_privilege(
    'anon', 'public.meeting_insights', 'SELECT'
  ) or pg_catalog.has_table_privilege(
    'anon', 'public.meeting_insights', 'INSERT'
  ) or pg_catalog.has_table_privilege(
    'anon', 'public.meeting_insights', 'UPDATE'
  ) or pg_catalog.has_table_privilege(
    'anon', 'public.meeting_insights', 'DELETE'
  ) then
    raise exception 'public or anon has unexpected meeting_insights privileges';
  end if;

  if not pg_catalog.has_table_privilege(
    'authenticated', 'public.meeting_insights', 'SELECT'
  ) or not pg_catalog.has_table_privilege(
    'authenticated', 'public.meeting_insights', 'INSERT'
  ) or not pg_catalog.has_table_privilege(
    'authenticated', 'public.meeting_insights', 'UPDATE'
  ) or not pg_catalog.has_table_privilege(
    'authenticated', 'public.meeting_insights', 'DELETE'
  ) then
    raise exception 'authenticated is missing required meeting_insights CRUD privileges';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_trigger
    where tgrelid = pg_catalog.to_regclass('public.meeting_insights')
      and tgname = 'meeting_insights_set_updated_at'
      and not tgisinternal
  ) then
    raise exception 'meeting_insights updated_at trigger is missing';
  end if;

  raise notice 'Phase 5 meeting insights schema verification passed.';
end;
$$;
