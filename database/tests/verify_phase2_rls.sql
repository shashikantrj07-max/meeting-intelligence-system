-- Behavioral verification using two existing Supabase Auth users.
-- Run against a non-production/test project with a database connection that
-- can SET ROLE authenticated. All test changes are rolled back.
--
-- psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--   -v user_a="UUID_FOR_TEST_USER_A" \
--   -v user_b="UUID_FOR_TEST_USER_B" \
--   -f database/tests/verify_phase2_rls.sql
--
-- Obtain IDs with:
-- select id, email from auth.users order by created_at desc limit 10;
-- Never create or delete Auth users solely for this test.

\if :{?user_a}
\else
\echo 'Provide -v user_a=<existing auth.users UUID>'
\quit 1
\endif
\if :{?user_b}
\else
\echo 'Provide -v user_b=<different existing auth.users UUID>'
\quit 1
\endif

\set ON_ERROR_STOP on
begin;

select set_config('request.jwt.claim.sub', :'user_a', true);
select set_config('app.test_user_a', :'user_a', true);
select set_config('app.test_user_b', :'user_b', true);

do $$
begin
  if current_setting('app.test_user_a')::uuid =
     current_setting('app.test_user_b')::uuid then
    raise exception 'User A and User B must be different Auth users';
  end if;
  if not exists (
    select 1 from auth.users
    where id = current_setting('app.test_user_a')::uuid
  ) or not exists (
    select 1 from auth.users
    where id = current_setting('app.test_user_b')::uuid
  ) then
    raise exception 'Both test IDs must belong to existing Auth users';
  end if;
  if not exists (
    select 1 from public.profiles
    where id = current_setting('app.test_user_a')::uuid
  ) or not exists (
    select 1 from public.profiles
    where id = current_setting('app.test_user_b')::uuid
  ) then
    raise exception 'Expected profile trigger/backfill to create both profiles';
  end if;
end;
$$;

set local role authenticated;

insert into public.meetings (owner_id, title)
values (:'user_a'::uuid, 'Phase 2 RLS verification')
returning id as test_meeting_id \gset

insert into public.meeting_participants (meeting_id, name)
values (:'test_meeting_id'::uuid, 'RLS test participant')
returning id as test_participant_id \gset

insert into public.meeting_files (
  meeting_id, storage_path, original_filename, file_size_bytes
)
values (:'test_meeting_id'::uuid, 'rls-test/file', 'recording.wav', 0)
returning id as test_file_id \gset

insert into public.meeting_processing (meeting_id)
values (:'test_meeting_id'::uuid)
returning id as test_processing_id \gset

select set_config('app.test_meeting_id', :'test_meeting_id', true);
select set_config('app.test_participant_id', :'test_participant_id', true);
select set_config('app.test_file_id', :'test_file_id', true);
select set_config('app.test_processing_id', :'test_processing_id', true);

do $$
begin
  if not exists (select 1 from public.profiles where id = auth.uid()) then
    raise exception 'User A cannot read their own profile';
  end if;
  if not exists (
    select 1 from public.meetings
    where id = current_setting('app.test_meeting_id', true)::uuid
      and owner_id = auth.uid()
  ) then
    raise exception 'User A cannot read their own meeting';
  end if;
end;
$$;

select set_config('request.jwt.claim.sub', :'user_b', true);

insert into public.meetings (owner_id, title)
values (:'user_b'::uuid, 'Phase 2 RLS verification for User B')
returning id as test_meeting_b_id \gset
select set_config('app.test_meeting_b_id', :'test_meeting_b_id', true);

do $$
declare
  affected integer;
begin
  if exists (select 1 from public.profiles where id = current_setting('app.test_user_a')::uuid) then
    raise exception 'User B can read User A profile';
  end if;
  update public.profiles
  set display_name = 'Unauthorized update'
  where id = current_setting('app.test_user_a')::uuid;
  get diagnostics affected = row_count;
  if affected <> 0 then
    raise exception 'User B updated User A profile';
  end if;
  if not exists (select 1 from public.profiles where id = auth.uid()) then
    raise exception 'User B cannot read their own profile';
  end if;
  if exists (select 1 from public.meetings where id = current_setting('app.test_meeting_id')::uuid) then
    raise exception 'User B can read User A meeting';
  end if;
  if not exists (
    select 1 from public.meetings
    where id = current_setting('app.test_meeting_b_id')::uuid
      and owner_id = auth.uid()
  ) then
    raise exception 'User B cannot read their own meeting';
  end if;
  if exists (select 1 from public.meeting_participants where id = current_setting('app.test_participant_id')::uuid) then
    raise exception 'User B can read User A participant';
  end if;
  if exists (select 1 from public.meeting_files where id = current_setting('app.test_file_id')::uuid) then
    raise exception 'User B can read User A file';
  end if;
  if exists (select 1 from public.meeting_processing where id = current_setting('app.test_processing_id')::uuid) then
    raise exception 'User B can read User A processing record';
  end if;

  update public.meetings
  set title = 'Unauthorized update'
  where id = current_setting('app.test_meeting_id')::uuid;
  get diagnostics affected = row_count;
  if affected <> 0 then
    raise exception 'User B updated User A meeting';
  end if;

  delete from public.meetings
  where id = current_setting('app.test_meeting_id')::uuid;
  get diagnostics affected = row_count;
  if affected <> 0 then
    raise exception 'User B deleted User A meeting';
  end if;

  update public.meeting_participants
  set name = 'Unauthorized update'
  where id = current_setting('app.test_participant_id')::uuid;
  get diagnostics affected = row_count;
  if affected <> 0 then
    raise exception 'User B updated User A participant';
  end if;
  delete from public.meeting_participants
  where id = current_setting('app.test_participant_id')::uuid;
  get diagnostics affected = row_count;
  if affected <> 0 then
    raise exception 'User B deleted User A participant';
  end if;

  update public.meeting_files
  set original_filename = 'unauthorized.wav'
  where id = current_setting('app.test_file_id')::uuid;
  get diagnostics affected = row_count;
  if affected <> 0 then
    raise exception 'User B updated User A file';
  end if;
  delete from public.meeting_files
  where id = current_setting('app.test_file_id')::uuid;
  get diagnostics affected = row_count;
  if affected <> 0 then
    raise exception 'User B deleted User A file';
  end if;

  update public.meeting_processing
  set stage = 'failed'
  where id = current_setting('app.test_processing_id')::uuid;
  get diagnostics affected = row_count;
  if affected <> 0 then
    raise exception 'User B updated User A processing record';
  end if;
  if pg_catalog.has_table_privilege(
    'authenticated', 'public.meeting_processing', 'DELETE'
  ) then
    raise exception 'Authenticated users unexpectedly have processing DELETE privilege';
  end if;

  begin
    insert into public.profiles (id)
    values (current_setting('app.test_user_a')::uuid);
    raise exception 'User B inserted User A profile';
  exception when insufficient_privilege then
    null;
  end;

  begin
    insert into public.meetings (owner_id, title)
    values (current_setting('app.test_user_a')::uuid, 'Unauthorized insert');
    raise exception 'User B inserted a meeting owned by User A';
  exception when insufficient_privilege then
    null;
  end;

  begin
    insert into public.meeting_participants (meeting_id, name)
    values (current_setting('app.test_meeting_id')::uuid, 'Unauthorized');
    raise exception 'User B inserted a participant into User A meeting';
  exception when insufficient_privilege then
    null;
  end;

  begin
    insert into public.meeting_files (meeting_id, storage_path, original_filename)
    values (current_setting('app.test_meeting_id')::uuid, 'unauthorized', 'bad.wav');
    raise exception 'User B inserted a file into User A meeting';
  exception when insufficient_privilege then
    null;
  end;

  begin
    insert into public.meeting_processing (meeting_id)
    values (current_setting('app.test_meeting_id')::uuid);
    raise exception 'User B inserted processing for User A meeting';
  exception when insufficient_privilege then
    null;
  end;

  begin
    update public.meetings
    set owner_id = current_setting('app.test_user_a')::uuid
    where id = current_setting('app.test_meeting_b_id')::uuid;
    raise exception 'User B transferred their meeting to User A';
  exception when insufficient_privilege then
    null;
  end;
end;
$$;

-- CHECK constraints are tested against the actual tables while authenticated.
do $$
declare
  own_meeting_id uuid;
begin
  own_meeting_id := current_setting('app.test_meeting_b_id')::uuid;

  begin
    insert into public.meetings (owner_id, title)
    values (auth.uid(), '   ');
    raise exception 'Blank meeting title was accepted';
  exception when check_violation then null;
  end;

  begin
    insert into public.meetings (owner_id, title, duration_seconds)
    values (auth.uid(), 'Invalid duration', -1);
    raise exception 'Negative meeting duration was accepted';
  exception when check_violation then null;
  end;

  begin
    insert into public.meetings (owner_id, title, status)
    values (auth.uid(), 'Invalid status', 'unknown');
    raise exception 'Invalid meeting status was accepted';
  exception when check_violation then null;
  end;

  begin
    insert into public.meeting_participants (meeting_id, name)
    values (own_meeting_id, ' ');
    raise exception 'Blank participant name was accepted';
  exception when check_violation then null;
  end;

  begin
    insert into public.meeting_files (meeting_id, storage_path, original_filename)
    values (own_meeting_id, ' ', 'file.wav');
    raise exception 'Blank storage path was accepted';
  exception when check_violation then null;
  end;

  begin
    insert into public.meeting_files (meeting_id, storage_path, original_filename)
    values (own_meeting_id, 'valid/path', ' ');
    raise exception 'Blank original filename was accepted';
  exception when check_violation then null;
  end;

  begin
    insert into public.meeting_files (
      meeting_id, storage_path, original_filename, file_size_bytes
    )
    values (own_meeting_id, 'valid/path', 'file.wav', -1);
    raise exception 'Negative file size was accepted';
  exception when check_violation then null;
  end;

  begin
    insert into public.meeting_processing (meeting_id, stage)
    values (own_meeting_id, 'unknown');
    raise exception 'Invalid processing stage was accepted';
  exception when check_violation then null;
  end;
end;
$$;

select set_config('request.jwt.claim.sub', :'user_a', true);

delete from public.meetings
where id = current_setting('app.test_meeting_id')::uuid;

do $$
begin
  if exists (
    select 1 from public.meeting_participants
    where id = current_setting('app.test_participant_id')::uuid
  ) or exists (
    select 1 from public.meeting_files
    where id = current_setting('app.test_file_id')::uuid
  ) or exists (
    select 1 from public.meeting_processing
    where id = current_setting('app.test_processing_id')::uuid
  ) then
    raise exception 'Deleting a meeting did not cascade to its child records';
  end if;
end;
$$;

rollback;
\echo 'Phase 2 RLS and CHECK behavior verification passed; test data rolled back.'
