-- Behavioral verification for Phase 11 durable processing jobs.
-- Run only against an approved disposable development/test project. All
-- database fixtures are created in a transaction and rolled back.
--
-- psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--   -v user_a="UUID_FOR_TEST_USER_A" \
--   -v user_b="UUID_FOR_TEST_USER_B" \
--   -f database/tests/verify_phase11_durable_processing_jobs.sql

\if :{?user_a}
\else
\echo 'Provide -v user_a=<existing auth.users UUID>'
\quit 1
\endif
\if :{?user_b}
\else
\echo 'Provide -v user_b=<different auth.users UUID>'
\quit 1
\endif

\set ON_ERROR_STOP on
begin;

select pg_catalog.set_config('request.jwt.claim.sub', :'user_a', true) is not null;
select pg_catalog.set_config('app.jobs_test_user_a', :'user_a', true) is not null;
select pg_catalog.set_config('app.jobs_test_user_b', :'user_b', true) is not null;

do $$
begin
  if current_setting('app.jobs_test_user_a')::uuid =
     current_setting('app.jobs_test_user_b')::uuid then
    raise exception 'User A and User B must be different Auth users';
  end if;
  if not exists (
    select 1 from auth.users
    where id = current_setting('app.jobs_test_user_a')::uuid
  ) or not exists (
    select 1 from auth.users
    where id = current_setting('app.jobs_test_user_b')::uuid
  ) then
    raise exception 'Both test IDs must belong to existing Auth users';
  end if;
  if not exists (
    select 1 from public.profiles
    where id = current_setting('app.jobs_test_user_a')::uuid
  ) or not exists (
    select 1 from public.profiles
    where id = current_setting('app.jobs_test_user_b')::uuid
  ) then
    raise exception 'Both test users must have profiles';
  end if;
end;
$$;

set local role authenticated;

insert into public.meetings (owner_id, title)
values
  (:'user_a'::uuid, 'Phase 11 durable job fixture A'),
  (:'user_b'::uuid, 'Phase 11 durable job fixture B');

select id as jobs_meeting_a
from public.meetings
where owner_id = :'user_a'::uuid
  and title = 'Phase 11 durable job fixture A'
\gset
select id as jobs_meeting_b
from public.meetings
where owner_id = :'user_b'::uuid
  and title = 'Phase 11 durable job fixture B'
\gset
select pg_catalog.set_config('app.jobs_meeting_a', :'jobs_meeting_a', true) is not null;
select pg_catalog.set_config('app.jobs_meeting_b', :'jobs_meeting_b', true) is not null;

insert into public.meeting_files (
  meeting_id,
  storage_path,
  original_filename,
  mime_type,
  file_size_bytes
)
values (
  :'jobs_meeting_a'::uuid,
  'phase11-test/recording.wav',
  'recording.wav',
  'audio/wav',
  1
)
returning id as jobs_file_a \gset
select pg_catalog.set_config('app.jobs_file_a', :'jobs_file_a', true) is not null;

select job_id as jobs_transcribe_id
from public.enqueue_meeting_processing_job(
  :'jobs_meeting_a'::uuid,
  'transcribe',
  :'jobs_file_a'::uuid,
  '33333333-3333-4333-8333-333333333333'::uuid
)
\gset
select pg_catalog.set_config(
  'app.jobs_transcribe_id',
  :'jobs_transcribe_id',
  true
) is not null;

select job_id as jobs_duplicate_id
from public.enqueue_meeting_processing_job(
  :'jobs_meeting_a'::uuid,
  'transcribe',
  :'jobs_file_a'::uuid,
  '33333333-3333-4333-8333-333333333333'::uuid
)
\gset
select pg_catalog.set_config(
  'app.jobs_duplicate_id',
  :'jobs_duplicate_id',
  true
) is not null;

do $$
begin
  if current_setting('app.jobs_transcribe_id')::uuid <>
     current_setting('app.jobs_duplicate_id')::uuid then
    raise exception 'Duplicate enqueue created a second active job';
  end if;
end;
$$;

select job_id as jobs_active_dedup_id
from public.enqueue_meeting_processing_job(
  :'jobs_meeting_a'::uuid,
  'transcribe',
  :'jobs_file_a'::uuid,
  '66666666-6666-4666-8666-666666666666'::uuid
)
\gset
select pg_catalog.set_config(
  'app.jobs_active_dedup_id',
  :'jobs_active_dedup_id',
  true
) is not null;

do $$
begin
  if current_setting('app.jobs_transcribe_id')::uuid <>
     current_setting('app.jobs_active_dedup_id')::uuid then
    raise exception 'A second active job was created for the meeting';
  end if;

  begin
    perform *
    from public.enqueue_meeting_processing_job(
      current_setting('app.jobs_meeting_a')::uuid,
      'insights',
      null,
      '33333333-3333-4333-8333-333333333333'::uuid
    );
    raise exception 'An idempotency key was reused for another job payload';
  exception when invalid_parameter_value then
    null;
  end;
end;
$$;

do $$
begin
  begin
    perform *
    from public.enqueue_meeting_processing_job(
      current_setting('app.jobs_meeting_a')::uuid,
      'insights',
      null,
      '44444444-4444-4444-8444-444444444444'::uuid
    );
    raise exception 'User B enqueued a job for User A meeting';
  exception when insufficient_privilege then
    null;
  end;
end;
$$;

select pg_catalog.set_config('request.jwt.claim.sub', :'user_b', true) is not null;
insert into public.meeting_transcripts (meeting_id, content)
values (
  :'jobs_meeting_b'::uuid,
  'A safe fixture transcript for user B.'
);
select job_id
from public.enqueue_meeting_processing_job(
  :'jobs_meeting_b'::uuid,
  'insights',
  null,
  '55555555-5555-4555-8555-555555555555'::uuid
);

do $$
begin
  if pg_catalog.has_table_privilege(
    'authenticated',
    'public.meeting_processing_jobs',
    'SELECT'
  ) then
    raise exception 'Authenticated users can read internal job records';
  end if;
  if pg_catalog.has_function_privilege(
    'authenticated',
    'public.claim_next_meeting_processing_job(uuid, integer)',
    'EXECUTE'
  ) then
    raise exception 'Authenticated users can claim worker jobs';
  end if;
end;
$$;

reset role;
set local role service_role;

select job_id, lease_token, attempt_count, attempt_started_at
from public.claim_next_meeting_processing_job(
  '11111111-1111-4111-8111-111111111111'::uuid,
  120
)
\gset
select pg_catalog.set_config('app.jobs_first_claim_id', :'job_id', true) is not null;
select pg_catalog.set_config('app.jobs_first_token', :'lease_token', true) is not null;
select pg_catalog.set_config('app.jobs_first_attempt', :'attempt_count', true) is not null;

select job_id as second_job_id
from public.claim_next_meeting_processing_job(
  '22222222-2222-4222-8222-222222222222'::uuid,
  120
)
\gset
select pg_catalog.set_config('app.jobs_second_claim_id', :'second_job_id', true) is not null;

do $$
begin
  if current_setting('app.jobs_first_claim_id')::uuid =
     current_setting('app.jobs_second_claim_id')::uuid then
    raise exception 'Two worker claims returned the same job';
  end if;
end;
$$;

reset role;
update public.meeting_processing_jobs
set lease_expires_at = pg_catalog.clock_timestamp() - interval '1 second'
where id = current_setting('app.jobs_first_claim_id')::uuid;

set local role service_role;
select job_id, lease_token, attempt_count, attempt_started_at
from public.claim_next_meeting_processing_job(
  '22222222-2222-4222-8222-222222222222'::uuid,
  120
)
\gset
select pg_catalog.set_config('app.jobs_reclaimed_id', :'job_id', true) is not null;
select pg_catalog.set_config('app.jobs_reclaimed_token', :'lease_token', true) is not null;
select pg_catalog.set_config('app.jobs_reclaimed_attempt', :'attempt_count', true) is not null;

do $$
declare
  old_attempt integer := current_setting('app.jobs_first_attempt')::integer;
  new_attempt integer := current_setting('app.jobs_reclaimed_attempt')::integer;
begin
  if current_setting('app.jobs_first_claim_id')::uuid <>
     current_setting('app.jobs_reclaimed_id')::uuid then
    raise exception 'Expired job was not recovered';
  end if;
  if new_attempt <> old_attempt + 1 then
    raise exception 'Recovered job attempt count did not increment';
  end if;
  if public.save_meeting_transcript_for_job(
    current_setting('app.jobs_reclaimed_id')::uuid,
    '11111111-1111-4111-8111-111111111111'::uuid,
    current_setting('app.jobs_first_token')::uuid,
    'Stale worker transcript'
  ) then
    raise exception 'Expired worker lease was allowed to save a transcript';
  end if;
end;
$$;

select public.save_meeting_transcript_for_job(
  current_setting('app.jobs_reclaimed_id')::uuid,
  '22222222-2222-4222-8222-222222222222'::uuid,
  current_setting('app.jobs_reclaimed_token')::uuid,
  'A safe fixture transcript.'
);

select public.complete_meeting_processing_job(
  current_setting('app.jobs_reclaimed_id')::uuid,
  '22222222-2222-4222-8222-222222222222'::uuid,
  current_setting('app.jobs_reclaimed_token')::uuid,
  '{
    "summary": "Fixture summary",
    "key_decisions": [],
    "action_items": [],
    "risks_blockers": [],
    "discussion_points": [],
    "open_questions": [],
    "next_steps": []
  }'::jsonb,
  '[{
    "identity_key": "0000000000000000000000000000000000000000000000000000000000000000",
    "text": "Fixture follow-up",
    "owner": null,
    "due_date": null,
    "priority": null,
    "evidence": null
  }]'::jsonb
);

do $$
begin
  if public.complete_meeting_processing_job(
    current_setting('app.jobs_reclaimed_id')::uuid,
    '22222222-2222-4222-8222-222222222222'::uuid,
    current_setting('app.jobs_reclaimed_token')::uuid,
    '{"summary":"Duplicate"}'::jsonb,
    '[]'::jsonb
  ) then
    raise exception 'Completed job accepted duplicate output persistence';
  end if;

  if (
    select count(*)
    from public.meeting_action_items
    where meeting_id = current_setting('app.jobs_meeting_a')::uuid
  ) <> 1 then
    raise exception 'Action-item output was not persisted exactly once';
  end if;
end;
$$;

select public.fail_meeting_processing_job(
  current_setting('app.jobs_second_claim_id')::uuid,
  '22222222-2222-4222-8222-222222222222'::uuid,
  (
    select lease_token
    from public.meeting_processing_jobs
    where id = current_setting('app.jobs_second_claim_id')::uuid
  ),
  true,
  'provider_unavailable',
  0
);

do $$
begin
  if not exists (
    select 1
    from public.meeting_processing_jobs
    where id = current_setting('app.jobs_second_claim_id')::uuid
      and status = 'retrying'
      and attempt_count = 1
  ) then
    raise exception 'Retryable failure was not scheduled';
  end if;
end;
$$;

reset role;
select pg_catalog.set_config('request.jwt.claim.sub', :'user_b', true) is not null;
set local role authenticated;

do $$
begin
  if not exists (
    select 1
    from public.search_my_meetings(
      'Phase 11 durable job fixture B',
      'processing',
      25
    ) as result
    where result.meeting_id =
      current_setting('app.jobs_meeting_b')::uuid
      and result.processing_stage = 'retrying'
  ) then
    raise exception 'Processing search omitted a retrying meeting';
  end if;
end;
$$;

rollback;
\echo 'Phase 11 durable processing checks passed; all fixtures rolled back.'
