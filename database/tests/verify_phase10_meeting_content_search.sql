-- Behavioral verification for Phase 10 meeting-content search.
-- Run only against a non-production development/test project. Test rows are
-- inserted under authenticated roles and rolled back at the end.
--
-- psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--   -v user_a="UUID_FOR_TEST_USER_A" \
--   -v user_b="UUID_FOR_TEST_USER_B" \
--   -f database/tests/verify_phase10_meeting_content_search.sql

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
select pg_catalog.set_config('app.search_test_user_a', :'user_a', true) is not null;
select pg_catalog.set_config('app.search_test_user_b', :'user_b', true) is not null;

do $$
begin
  if current_setting('app.search_test_user_a')::uuid =
     current_setting('app.search_test_user_b')::uuid then
    raise exception 'User A and User B must be different Auth users';
  end if;
  if not exists (
    select 1 from auth.users
    where id = current_setting('app.search_test_user_a')::uuid
  ) or not exists (
    select 1 from auth.users
    where id = current_setting('app.search_test_user_b')::uuid
  ) then
    raise exception 'Both test IDs must belong to existing Auth users';
  end if;
  if not exists (
    select 1 from public.profiles
    where id = current_setting('app.search_test_user_a')::uuid
  ) or not exists (
    select 1 from public.profiles
    where id = current_setting('app.search_test_user_b')::uuid
  ) then
    raise exception 'Both test users must have profiles';
  end if;
end;
$$;

set local role authenticated;

insert into public.meetings (owner_id, title)
values
  (:'user_a'::uuid, 'Phase 10 search title unique marker'),
  (:'user_a'::uuid, 'Phase 10 literal 100%_ title marker'),
  (:'user_a'::uuid, 'Phase 10 search transcript fixture'),
  (:'user_a'::uuid, 'Phase 10 search bounded fixture one'),
  (:'user_a'::uuid, 'Phase 10 search bounded fixture two');

-- Save the fixture IDs without relying on INSERT return order.
select id as search_title_meeting_id
from public.meetings
where owner_id = :'user_a'::uuid
  and title = 'Phase 10 search title unique marker'
\gset
select pg_catalog.set_config(
  'app.search_title_meeting_id',
  :'search_title_meeting_id',
  true
) is not null;
select id as search_transcript_meeting_id
from public.meetings
where owner_id = :'user_a'::uuid
  and title = 'Phase 10 search transcript fixture'
\gset
select pg_catalog.set_config(
  'app.search_transcript_meeting_id',
  :'search_transcript_meeting_id',
  true
) is not null;

insert into public.meeting_transcripts (meeting_id, content)
values (
  :'search_transcript_meeting_id'::uuid,
  'The unique transcript phrase missearchtranscriptmarker appears in this discussion.'
);

do $$
declare
  actual_count integer;
begin
  if not exists (
    select 1
    from public.search_my_meetings(
      'unique marker',
      'all',
      25
    ) as result
    where result.meeting_id =
      current_setting('app.search_title_meeting_id', true)::uuid
      and result.matched_in = 'title'
  ) then
    raise exception 'Title-only matching failed';
  end if;

  if not exists (
    select 1
    from public.search_my_meetings('100%_', 'all', 25) as result
    where result.title = 'Phase 10 literal 100%_ title marker'
      and result.matched_in = 'title'
  ) then
    raise exception 'Literal percent/underscore title matching failed';
  end if;

  if not exists (
    select 1
    from public.search_my_meetings(
      'missearchtranscriptmarker',
      'all',
      25
    ) as result
    where result.meeting_id =
      current_setting('app.search_transcript_meeting_id', true)::uuid
      and result.matched_in = 'transcript'
      and result.search_context is not null
  ) then
    raise exception 'Transcript-only matching or context failed';
  end if;

  select count(*) into actual_count
  from public.search_my_meetings(
    'missearchnothingmatches',
    'all',
    25
  );
  if actual_count <> 0 then
    raise exception 'No-results query returned unexpected meetings';
  end if;

  select count(*) into actual_count
  from public.search_my_meetings('phase 10 search bounded', 'all', 1);
  if actual_count <> 1 then
    raise exception 'Search result limit was not enforced';
  end if;

  begin
    perform * from public.search_my_meetings('', 'all', 25);
    raise exception 'Empty search query was accepted';
  exception when invalid_parameter_value then
    null;
  end;
end;
$$;

select pg_catalog.set_config('request.jwt.claim.sub', :'user_b', true) is not null;

do $$
begin
  if exists (
    select 1
    from public.search_my_meetings(
      'missearchtranscriptmarker',
      'all',
      25
    )
  ) then
    raise exception 'User B received a result from User A transcript';
  end if;
end;
$$;

rollback;
\echo 'Phase 10 meeting-content search checks passed; test data rolled back.'
