-- Run after applying 20261022000100_phase4_meeting_transcripts.sql.
-- psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--   -f database/tests/verify_phase4_transcripts.sql

do $$
declare
  expected_policy text;
begin
  if pg_catalog.to_regclass('public.meeting_transcripts') is null then
    raise exception 'Missing table public.meeting_transcripts';
  end if;

  if not (
    select relrowsecurity
    from pg_catalog.pg_class
    where oid = pg_catalog.to_regclass('public.meeting_transcripts')
  ) then
    raise exception 'RLS is not enabled on public.meeting_transcripts';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_constraint
    where conrelid = pg_catalog.to_regclass('public.meeting_transcripts')
      and conname = 'meeting_transcripts_meeting_id_key'
      and contype = 'u'
  ) then
    raise exception 'Transcript meeting_id is not unique';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_constraint
    where conrelid = pg_catalog.to_regclass('public.meeting_transcripts')
      and conname = 'meeting_transcripts_meeting_id_fkey'
      and contype = 'f'
      and confrelid = 'public.meetings'::regclass
      and confdeltype = 'c'
  ) then
    raise exception 'Transcript meeting foreign key does not cascade';
  end if;

  if not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'meeting_transcripts'
      and column_name = 'content'
      and is_nullable = 'NO'
  ) then
    raise exception 'Transcript content must be NOT NULL';
  end if;

  foreach expected_policy in array array[
    'meeting_transcripts_select_own',
    'meeting_transcripts_insert_own',
    'meeting_transcripts_update_own',
    'meeting_transcripts_delete_own'
  ]
  loop
    if not exists (
      select 1
      from pg_catalog.pg_policies
      where schemaname = 'public'
        and tablename = 'meeting_transcripts'
        and policyname = expected_policy
        and roles = array['authenticated']::name[]
    ) then
      raise exception 'Missing authenticated ownership policy %', expected_policy;
    end if;
  end loop;

  if pg_catalog.has_table_privilege(
    'anon', 'public.meeting_transcripts', 'SELECT'
  ) or pg_catalog.has_table_privilege(
    'anon', 'public.meeting_transcripts', 'INSERT'
  ) or pg_catalog.has_table_privilege(
    'anon', 'public.meeting_transcripts', 'UPDATE'
  ) or pg_catalog.has_table_privilege(
    'anon', 'public.meeting_transcripts', 'DELETE'
  ) then
    raise exception 'anon has unexpected transcript table privileges';
  end if;

  if not pg_catalog.has_table_privilege(
    'authenticated', 'public.meeting_transcripts', 'SELECT'
  ) or not pg_catalog.has_table_privilege(
    'authenticated', 'public.meeting_transcripts', 'INSERT'
  ) or not pg_catalog.has_table_privilege(
    'authenticated', 'public.meeting_transcripts', 'UPDATE'
  ) or not pg_catalog.has_table_privilege(
    'authenticated', 'public.meeting_transcripts', 'DELETE'
  ) then
    raise exception 'authenticated is missing transcript table privileges';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_trigger
    where tgrelid = 'public.meeting_transcripts'::regclass
      and tgname = 'meeting_transcripts_set_updated_at'
      and not tgisinternal
  ) then
    raise exception 'Transcript updated_at trigger is missing';
  end if;

  raise notice 'Phase 4 transcript schema verification passed.';
end;
$$;
