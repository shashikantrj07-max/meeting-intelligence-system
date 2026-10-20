-- Run after applying migrations, for example:
-- psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/tests/verify_schema.sql
-- This checks catalog definitions; verify_phase2_rls.sql tests behavior.

do $$
declare
  v_table_name text;
  v_column_name text;
  expected_name text;
  expected_fk record;
  expected_privilege record;
begin
  foreach v_table_name in array array[
    'profiles',
    'meetings',
    'meeting_participants',
    'meeting_files',
    'meeting_processing'
  ]
  loop
    if pg_catalog.to_regclass('public.' || v_table_name) is null then
      raise exception 'Missing table public.%', v_table_name;
    end if;

    if not exists (
      select 1
      from pg_catalog.pg_constraint
      where conrelid = pg_catalog.to_regclass('public.' || v_table_name)
        and contype = 'p'
    ) then
      raise exception 'Missing primary key on public.%', v_table_name;
    end if;

    if not (
      select relrowsecurity
      from pg_catalog.pg_class
      where oid = pg_catalog.to_regclass('public.' || v_table_name)
    ) then
      raise exception 'RLS is not enabled on public.%', v_table_name;
    end if;
  end loop;

  for expected_privilege in
    select *
    from (values
      ('profiles', 'SELECT', true),
      ('profiles', 'INSERT', true),
      ('profiles', 'UPDATE', true),
      ('profiles', 'DELETE', false),
      ('meetings', 'SELECT', true),
      ('meetings', 'INSERT', true),
      ('meetings', 'UPDATE', true),
      ('meetings', 'DELETE', true),
      ('meeting_participants', 'SELECT', true),
      ('meeting_participants', 'INSERT', true),
      ('meeting_participants', 'UPDATE', true),
      ('meeting_participants', 'DELETE', true),
      ('meeting_files', 'SELECT', true),
      ('meeting_files', 'INSERT', true),
      ('meeting_files', 'UPDATE', true),
      ('meeting_files', 'DELETE', true),
      ('meeting_processing', 'SELECT', true),
      ('meeting_processing', 'INSERT', true),
      ('meeting_processing', 'UPDATE', true),
      ('meeting_processing', 'DELETE', false)
    ) as privileges(table_name, privilege, granted)
  loop
    if pg_catalog.has_table_privilege(
      'anon',
      'public.' || expected_privilege.table_name,
      expected_privilege.privilege
    ) then
      raise exception 'anon unexpectedly has % on public.%',
        expected_privilege.privilege, expected_privilege.table_name;
    end if;
    if pg_catalog.has_table_privilege(
      'authenticated',
      'public.' || expected_privilege.table_name,
      expected_privilege.privilege
    ) is distinct from expected_privilege.granted then
      raise exception 'Unexpected authenticated % privilege on public.%',
        expected_privilege.privilege, expected_privilege.table_name;
    end if;
  end loop;

  for v_table_name, v_column_name in
    select required.table_name, required.column_name
    from (values
      ('profiles', 'id'),
      ('profiles', 'created_at'),
      ('profiles', 'updated_at'),
      ('meetings', 'id'),
      ('meetings', 'owner_id'),
      ('meetings', 'title'),
      ('meetings', 'status'),
      ('meetings', 'created_at'),
      ('meetings', 'updated_at'),
      ('meeting_participants', 'id'),
      ('meeting_participants', 'meeting_id'),
      ('meeting_participants', 'name'),
      ('meeting_participants', 'created_at'),
      ('meeting_files', 'id'),
      ('meeting_files', 'meeting_id'),
      ('meeting_files', 'storage_path'),
      ('meeting_files', 'original_filename'),
      ('meeting_files', 'created_at'),
      ('meeting_processing', 'id'),
      ('meeting_processing', 'meeting_id'),
      ('meeting_processing', 'stage'),
      ('meeting_processing', 'created_at'),
      ('meeting_processing', 'updated_at')
    ) as required(table_name, column_name)
  loop
    if not exists (
      select 1
      from information_schema.columns
      where table_schema = 'public'
        and columns.table_name = v_table_name
        and columns.column_name = v_column_name
        and is_nullable = 'NO'
      ) then
      raise exception 'Expected NOT NULL on public.%.%', v_table_name, v_column_name;
    end if;
  end loop;

  for expected_fk in
    select * from (values
      ('profiles', 'profiles_id_fkey', 'auth.users'),
      ('meetings', 'meetings_owner_id_fkey', 'public.profiles'),
      ('meeting_participants', 'meeting_participants_meeting_id_fkey', 'public.meetings'),
      ('meeting_files', 'meeting_files_meeting_id_fkey', 'public.meetings'),
      ('meeting_processing', 'meeting_processing_meeting_id_fkey', 'public.meetings')
    ) as fks(table_name, constraint_name, referenced_table)
  loop
    if not exists (
      select 1
      from pg_catalog.pg_constraint as c
      where c.conrelid = pg_catalog.to_regclass('public.' || expected_fk.table_name)
        and c.conname = expected_fk.constraint_name
        and c.contype = 'f'
        and c.confrelid = pg_catalog.to_regclass(expected_fk.referenced_table)
        and c.confdeltype = 'c'
    ) then
      raise exception 'Missing expected cascading foreign key %', expected_fk.constraint_name;
    end if;
  end loop;

  for expected_name in
    select expected.constraint_name
    from (values
      ('meetings_title_not_blank'),
      ('meetings_duration_nonnegative'),
      ('meetings_status_valid'),
      ('meeting_participants_name_not_blank'),
      ('meeting_files_storage_path_not_blank'),
      ('meeting_files_filename_not_blank'),
      ('meeting_files_size_nonnegative'),
      ('meeting_processing_stage_valid')
    ) as expected(constraint_name)
  loop
    if not exists (
      select 1 from pg_catalog.pg_constraint
      where conname = expected_name and contype = 'c'
    ) then
      raise exception 'Missing CHECK constraint %', expected_name;
    end if;
  end loop;

  for expected_name in
    select expected.policy_name
    from (values
      ('profiles_select_own'),
      ('profiles_insert_own'),
      ('profiles_update_own'),
      ('meetings_select_own'),
      ('meetings_insert_own'),
      ('meetings_update_own'),
      ('meetings_delete_own'),
      ('meeting_participants_select_own'),
      ('meeting_participants_insert_own'),
      ('meeting_participants_update_own'),
      ('meeting_participants_delete_own'),
      ('meeting_files_select_own'),
      ('meeting_files_insert_own'),
      ('meeting_files_update_own'),
      ('meeting_files_delete_own'),
      ('meeting_processing_select_own'),
      ('meeting_processing_insert_own'),
      ('meeting_processing_update_own')
    ) as expected(policy_name)
  loop
    if not exists (
      select 1 from pg_catalog.pg_policies
      where schemaname = 'public' and policyname = expected_name
    ) then
      raise exception 'Missing RLS policy %', expected_name;
    end if;
  end loop;

  if not exists (
    select 1 from pg_catalog.pg_indexes
    where schemaname = 'public' and indexname = 'meetings_owner_id_idx'
  ) or not exists (
    select 1 from pg_catalog.pg_indexes
    where schemaname = 'public' and indexname = 'meetings_owner_created_at_idx'
  ) or not exists (
    select 1 from pg_catalog.pg_indexes
    where schemaname = 'public' and indexname = 'meeting_participants_meeting_id_idx'
  ) or not exists (
    select 1 from pg_catalog.pg_indexes
    where schemaname = 'public' and indexname = 'meeting_files_meeting_id_idx'
  ) then
    raise exception 'A required ownership or meeting foreign-key index is missing';
  end if;

  if not exists (
    select 1 from pg_catalog.pg_indexes
    where schemaname = 'public' and indexname = 'meeting_processing_meeting_id_key'
  ) then
    raise exception 'Unique meeting_processing.meeting_id index is missing';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_trigger
    where tgrelid = 'auth.users'::regclass
      and tgname = 'on_auth_user_created'
      and not tgisinternal
  ) then
    raise exception 'Auth profile creation trigger is missing';
  end if;

  raise notice 'Phase 2 database schema verification passed.';
end;
$$;
