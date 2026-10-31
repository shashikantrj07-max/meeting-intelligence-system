alter table public.meeting_processing
  drop constraint meeting_processing_stage_valid;

alter table public.meeting_processing
  add constraint meeting_processing_stage_valid check (
    stage in (
      'pending',
      'transcribing',
      'analyzing',
      'retrying',
      'completed',
      'failed'
    )
  );

create table public.meeting_processing_jobs (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete cascade,
  meeting_id uuid not null references public.meetings (id) on delete cascade,
  file_id uuid references public.meeting_files (id) on delete cascade,
  idempotency_key uuid not null,
  job_type text not null,
  status text not null default 'pending',
  attempt_count integer not null default 0,
  max_attempts integer not null default 3,
  available_at timestamptz not null default pg_catalog.clock_timestamp(),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  started_at timestamptz,
  attempt_started_at timestamptz,
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  completed_at timestamptz,
  lease_owner uuid,
  lease_token uuid,
  lease_expires_at timestamptz,
  error_category text,
  constraint meeting_processing_jobs_type_valid check (
    job_type in ('transcribe', 'insights')
  ),
  constraint meeting_processing_jobs_status_valid check (
    status in ('pending', 'running', 'retrying', 'completed', 'failed')
  ),
  constraint meeting_processing_jobs_attempts_valid check (
    attempt_count >= 0 and max_attempts between 1 and 5
  ),
  constraint meeting_processing_jobs_file_valid check (
    (job_type = 'transcribe' and file_id is not null)
    or (job_type = 'insights' and file_id is null)
  ),
  constraint meeting_processing_jobs_owner_idempotency_unique
    unique (owner_id, idempotency_key),
  constraint meeting_processing_jobs_lease_valid check (
    (status = 'running'
      and lease_owner is not null
      and lease_token is not null
      and lease_expires_at is not null
      and attempt_started_at is not null)
    or
    (status <> 'running'
      and lease_owner is null
      and lease_token is null
      and lease_expires_at is null)
  )
);

create unique index meeting_processing_jobs_one_active_per_meeting_idx
  on public.meeting_processing_jobs (meeting_id)
  where status in ('pending', 'running', 'retrying');

create index meeting_processing_jobs_ready_idx
  on public.meeting_processing_jobs (available_at, created_at)
  where status in ('pending', 'retrying');

create index meeting_processing_jobs_expired_lease_idx
  on public.meeting_processing_jobs (lease_expires_at)
  where status = 'running';

alter table public.meeting_processing_jobs enable row level security;
revoke all on table public.meeting_processing_jobs from public, anon, authenticated;

create function public.enqueue_meeting_processing_job(
  p_meeting_id uuid,
  p_job_type text,
  p_file_id uuid,
  p_idempotency_key uuid
)
returns table (job_id uuid, job_status text)
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  current_user_id uuid := auth.uid();
  meeting_owner_id uuid;
  active_job_id uuid;
  active_job_status text;
  inserted_job_id uuid;
  inserted_job_status text;
begin
  if current_user_id is null then
    raise exception using errcode = '42501', message = 'Authentication required';
  end if;

  if p_job_type is null or p_job_type not in ('transcribe', 'insights') then
    raise exception using errcode = '22023', message = 'Invalid processing job type';
  end if;
  if p_idempotency_key is null then
    raise exception using errcode = '22023', message = 'Idempotency key is required';
  end if;

  select m.owner_id
  into meeting_owner_id
  from public.meetings as m
  where m.id = p_meeting_id;

  if meeting_owner_id is distinct from current_user_id then
    raise exception using errcode = '42501', message = 'Meeting is inaccessible';
  end if;

  if p_job_type = 'transcribe' then
    if p_file_id is null or not exists (
      select 1
      from public.meeting_files as f
      where f.id = p_file_id
        and f.meeting_id = p_meeting_id
    ) then
      raise exception using errcode = '22023', message = 'Invalid meeting file';
    end if;
  elsif p_file_id is not null or not exists (
    select 1
    from public.meeting_transcripts as t
    where t.meeting_id = p_meeting_id
  ) then
    raise exception using errcode = '22023', message = 'Meeting transcript is required';
  end if;

  select j.id, j.status
  into active_job_id, active_job_status
  from public.meeting_processing_jobs as j
  where j.owner_id = current_user_id
    and j.idempotency_key = p_idempotency_key;

  if active_job_id is not null then
    if not exists (
      select 1
      from public.meeting_processing_jobs as j
      where j.id = active_job_id
        and j.meeting_id = p_meeting_id
        and j.job_type = p_job_type
        and j.file_id is not distinct from p_file_id
    ) then
      raise exception using errcode = '22023', message = 'Idempotency key is already in use';
    end if;
    return query select active_job_id, active_job_status;
    return;
  end if;

  select j.id, j.status
  into active_job_id, active_job_status
  from public.meeting_processing_jobs as j
  where j.meeting_id = p_meeting_id
    and j.status in ('pending', 'running', 'retrying')
  limit 1;

  if active_job_id is not null then
    return query select active_job_id, active_job_status;
    return;
  end if;

  insert into public.meeting_processing_jobs (
    owner_id,
    meeting_id,
    file_id,
    job_type,
    idempotency_key
  )
  values (
    current_user_id,
    p_meeting_id,
    p_file_id,
    p_job_type,
    p_idempotency_key
  )
  on conflict do nothing
  returning id, status
  into inserted_job_id, inserted_job_status;

  if inserted_job_id is null then
    select j.id, j.status
    into active_job_id, active_job_status
    from public.meeting_processing_jobs as j
    where j.owner_id = current_user_id
      and j.idempotency_key = p_idempotency_key;

    if active_job_id is not null then
      if not exists (
        select 1
        from public.meeting_processing_jobs as j
        where j.id = active_job_id
          and j.meeting_id = p_meeting_id
          and j.job_type = p_job_type
          and j.file_id is not distinct from p_file_id
      ) then
        raise exception using errcode = '22023', message = 'Idempotency key is already in use';
      end if;
      return query select active_job_id, active_job_status;
      return;
    end if;

    select j.id, j.status
    into active_job_id, active_job_status
    from public.meeting_processing_jobs as j
    where j.meeting_id = p_meeting_id
      and j.status in ('pending', 'running', 'retrying')
    limit 1;

    return query select active_job_id, active_job_status;
    return;
  end if;

  insert into public.meeting_processing (
    meeting_id,
    stage,
    started_at,
    completed_at,
    error_message
  )
  values (
    p_meeting_id,
    'pending',
    null,
    null,
    null
  )
  on conflict (meeting_id) do update
  set stage = 'pending',
      started_at = null,
      completed_at = null,
      error_message = null;

  return query select inserted_job_id, inserted_job_status;
end;
$$;

create function public.claim_next_meeting_processing_job(
  p_worker_id uuid,
  p_lease_seconds integer default 90
)
returns table (
  job_id uuid,
  meeting_id uuid,
  job_type text,
  file_id uuid,
  attempt_count integer,
  max_attempts integer,
  lease_token uuid,
  attempt_started_at timestamptz
)
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  selected_job public.meeting_processing_jobs%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
  new_lease_token uuid;
begin
  if p_worker_id is null or p_lease_seconds not between 60 and 3600 then
    raise exception using errcode = '22023', message = 'Invalid worker lease';
  end if;

  update public.meeting_processing_jobs as j
  set status = 'failed',
      completed_at = now_at,
      updated_at = now_at,
      lease_owner = null,
      lease_token = null,
      lease_expires_at = null,
      error_category = 'attempts_exhausted'
  where j.status = 'running'
    and j.lease_expires_at <= now_at
    and j.attempt_count >= j.max_attempts;

  update public.meeting_processing as p
  set stage = 'failed',
      completed_at = now_at,
      error_message = 'Meeting processing failed. You can try again.'
  where p.meeting_id in (
    select j.meeting_id
    from public.meeting_processing_jobs as j
    where j.status = 'failed'
      and j.error_category = 'attempts_exhausted'
      and p.started_at is not distinct from j.attempt_started_at
  );

  select j.*
  into selected_job
  from public.meeting_processing_jobs as j
  where (
      j.status in ('pending', 'retrying')
      and j.available_at <= now_at
    )
    or (
      j.status = 'running'
      and j.lease_expires_at <= now_at
      and j.attempt_count < j.max_attempts
    )
  order by j.available_at, j.created_at
  limit 1
  for update skip locked;

  if not found then
    return;
  end if;

  new_lease_token := pg_catalog.gen_random_uuid();

  update public.meeting_processing_jobs as j
  set status = 'running',
      attempt_count = j.attempt_count + 1,
      started_at = coalesce(j.started_at, now_at),
      attempt_started_at = now_at,
      updated_at = now_at,
      lease_owner = p_worker_id,
      lease_token = new_lease_token,
      lease_expires_at = now_at + pg_catalog.make_interval(secs => p_lease_seconds),
      error_category = null
  where j.id = selected_job.id;

  insert into public.meeting_processing (
    meeting_id,
    stage,
    started_at,
    completed_at,
    error_message
  )
  values (
    selected_job.meeting_id,
    case when selected_job.job_type = 'transcribe' then 'transcribing' else 'analyzing' end,
    now_at,
    null,
    null
  )
  on conflict (meeting_id) do update
  set stage = excluded.stage,
      started_at = excluded.started_at,
      completed_at = null,
      error_message = null;

  return query
  select
    j.id,
    j.meeting_id,
    j.job_type,
    j.file_id,
    j.attempt_count,
    j.max_attempts,
    j.lease_token,
    j.attempt_started_at
  from public.meeting_processing_jobs as j
  where j.id = selected_job.id;
end;
$$;

create function public.renew_meeting_processing_job_lease(
  p_job_id uuid,
  p_worker_id uuid,
  p_lease_token uuid,
  p_lease_seconds integer default 90
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog
as $$
begin
  if p_lease_seconds not between 60 and 3600 then
    raise exception using errcode = '22023', message = 'Invalid worker lease';
  end if;

  update public.meeting_processing_jobs as j
  set lease_expires_at = pg_catalog.clock_timestamp()
        + pg_catalog.make_interval(secs => p_lease_seconds),
      updated_at = pg_catalog.clock_timestamp()
  where j.id = p_job_id
    and j.status = 'running'
    and j.lease_owner = p_worker_id
    and j.lease_token = p_lease_token
    and j.lease_expires_at > pg_catalog.clock_timestamp();

  return found;
end;
$$;

create function public.save_meeting_transcript_for_job(
  p_job_id uuid,
  p_worker_id uuid,
  p_lease_token uuid,
  p_transcript text
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  current_job public.meeting_processing_jobs%rowtype;
begin
  select j.*
  into current_job
  from public.meeting_processing_jobs as j
  where j.id = p_job_id
    and j.status = 'running'
    and j.job_type = 'transcribe'
    and j.lease_owner = p_worker_id
    and j.lease_token = p_lease_token
    and j.lease_expires_at > pg_catalog.clock_timestamp()
  for update;

  if not found then
    return false;
  end if;

  if p_transcript is null or pg_catalog.btrim(p_transcript) = '' then
    raise exception using errcode = '22023', message = 'Transcript is empty';
  end if;

  insert into public.meeting_transcripts (meeting_id, content)
  values (current_job.meeting_id, p_transcript)
  on conflict (meeting_id) do update
  set content = excluded.content;

  update public.meeting_processing as p
  set stage = 'analyzing',
      started_at = current_job.attempt_started_at,
      completed_at = null,
      error_message = null
  where p.meeting_id = current_job.meeting_id;

  return true;
end;
$$;

create function public.complete_meeting_processing_job(
  p_job_id uuid,
  p_worker_id uuid,
  p_lease_token uuid,
  p_insights jsonb,
  p_action_items jsonb
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  current_job public.meeting_processing_jobs%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  select j.*
  into current_job
  from public.meeting_processing_jobs as j
  where j.id = p_job_id
    and j.status = 'running'
    and j.lease_owner = p_worker_id
    and j.lease_token = p_lease_token
    and j.lease_expires_at > now_at
  for update;

  if not found then
    return false;
  end if;

  if p_insights is null
     or pg_catalog.jsonb_typeof(p_insights) <> 'object'
     or p_action_items is null
     or pg_catalog.jsonb_typeof(p_action_items) <> 'array' then
    raise exception using errcode = '22023', message = 'Invalid meeting insights';
  end if;

  insert into public.meeting_insights (
    meeting_id,
    summary,
    key_decisions,
    action_items,
    risks_blockers,
    discussion_points,
    open_questions,
    next_steps
  )
  values (
    current_job.meeting_id,
    p_insights->>'summary',
    coalesce(p_insights->'key_decisions', '[]'::jsonb),
    coalesce(p_insights->'action_items', '[]'::jsonb),
    coalesce(p_insights->'risks_blockers', '[]'::jsonb),
    coalesce(p_insights->'discussion_points', '[]'::jsonb),
    coalesce(p_insights->'open_questions', '[]'::jsonb),
    coalesce(p_insights->'next_steps', '[]'::jsonb)
  )
  on conflict (meeting_id) do update
  set summary = excluded.summary,
      key_decisions = excluded.key_decisions,
      action_items = excluded.action_items,
      risks_blockers = excluded.risks_blockers,
      discussion_points = excluded.discussion_points,
      open_questions = excluded.open_questions,
      next_steps = excluded.next_steps;

  if pg_catalog.jsonb_array_length(p_action_items) > 0 then
    insert into public.meeting_action_items (
      meeting_id,
      identity_key,
      text,
      owner,
      due_date,
      priority,
      evidence
    )
    select
      current_job.meeting_id,
      item->>'identity_key',
      item->>'text',
      item->>'owner',
      item->>'due_date',
      item->>'priority',
      item->>'evidence'
    from pg_catalog.jsonb_array_elements(p_action_items) as items(item)
    on conflict (meeting_id, identity_key) do update
    set text = excluded.text,
        owner = excluded.owner,
        due_date = excluded.due_date,
        priority = excluded.priority,
        evidence = excluded.evidence;
  end if;

  update public.meeting_processing_jobs as j
  set status = 'completed',
      completed_at = now_at,
      updated_at = now_at,
      lease_owner = null,
      lease_token = null,
      lease_expires_at = null,
      error_category = null
  where j.id = current_job.id;

  update public.meeting_processing as p
  set stage = 'completed',
      completed_at = now_at,
      error_message = null
  where p.meeting_id = current_job.meeting_id
    and p.started_at = current_job.attempt_started_at;

  return true;
end;
$$;

create function public.fail_meeting_processing_job(
  p_job_id uuid,
  p_worker_id uuid,
  p_lease_token uuid,
  p_retryable boolean,
  p_error_category text,
  p_retry_delay_seconds integer default 0
)
returns text
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  current_job public.meeting_processing_jobs%rowtype;
  next_status text;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_error_category not in (
    'provider_unavailable',
    'storage_unavailable',
    'processing_failed',
    'invalid_input',
    'authorization_failed',
    'attempts_exhausted'
  ) then
    raise exception using errcode = '22023', message = 'Invalid error category';
  end if;
  if p_retry_delay_seconds not between 0 and 3600 then
    raise exception using errcode = '22023', message = 'Invalid retry delay';
  end if;

  select j.*
  into current_job
  from public.meeting_processing_jobs as j
  where j.id = p_job_id
    and j.status = 'running'
    and j.lease_owner = p_worker_id
    and j.lease_token = p_lease_token
    and j.lease_expires_at > now_at
  for update;

  if not found then
    return 'superseded';
  end if;

  if p_retryable and current_job.attempt_count < current_job.max_attempts then
    next_status := 'retrying';
    update public.meeting_processing_jobs as j
    set status = next_status,
        available_at = now_at
          + pg_catalog.make_interval(secs => p_retry_delay_seconds),
        updated_at = now_at,
        lease_owner = null,
        lease_token = null,
        lease_expires_at = null,
        error_category = p_error_category
    where j.id = current_job.id;

    update public.meeting_processing as p
    set stage = 'retrying',
        completed_at = null,
        error_message = 'A temporary issue occurred. Processing will retry.'
    where p.meeting_id = current_job.meeting_id
      and p.started_at = current_job.attempt_started_at;
  else
    next_status := 'failed';
    update public.meeting_processing_jobs as j
    set status = next_status,
        completed_at = now_at,
        updated_at = now_at,
        lease_owner = null,
        lease_token = null,
        lease_expires_at = null,
        error_category = case
          when p_retryable then 'attempts_exhausted'
          else p_error_category
        end
    where j.id = current_job.id;

    update public.meeting_processing as p
    set stage = 'failed',
        completed_at = now_at,
        error_message = 'Meeting processing failed. You can try again.'
    where p.meeting_id = current_job.meeting_id
      and p.started_at = current_job.attempt_started_at;
  end if;

  return next_status;
end;
$$;

revoke all on function public.enqueue_meeting_processing_job(uuid, text, uuid, uuid)
  from public, anon;
grant execute on function public.enqueue_meeting_processing_job(uuid, text, uuid, uuid)
  to authenticated;

revoke all on function public.claim_next_meeting_processing_job(uuid, integer)
  from public, anon, authenticated;
grant execute on function public.claim_next_meeting_processing_job(uuid, integer)
  to service_role;

revoke all on function public.renew_meeting_processing_job_lease(uuid, uuid, uuid, integer)
  from public, anon, authenticated;
grant execute on function public.renew_meeting_processing_job_lease(uuid, uuid, uuid, integer)
  to service_role;

revoke all on function public.save_meeting_transcript_for_job(uuid, uuid, uuid, text)
  from public, anon, authenticated;
grant execute on function public.save_meeting_transcript_for_job(uuid, uuid, uuid, text)
  to service_role;

revoke all on function public.complete_meeting_processing_job(uuid, uuid, uuid, jsonb, jsonb)
  from public, anon, authenticated;
grant execute on function public.complete_meeting_processing_job(uuid, uuid, uuid, jsonb, jsonb)
  to service_role;

revoke all on function public.fail_meeting_processing_job(uuid, uuid, uuid, boolean, text, integer)
  from public, anon, authenticated;
grant execute on function public.fail_meeting_processing_job(uuid, uuid, uuid, boolean, text, integer)
  to service_role;
