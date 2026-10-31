create or replace function public.claim_next_meeting_processing_job(
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
  on conflict on constraint meeting_processing_meeting_id_key do update
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
