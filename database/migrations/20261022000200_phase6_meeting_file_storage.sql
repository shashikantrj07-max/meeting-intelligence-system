-- Phase 6: private Storage for meeting audio/video files.
-- Objects are addressable only when their path has an owner-authorized
-- public.meeting_files row linked to a meeting owned by auth.uid().

create unique index if not exists meeting_files_storage_path_key
  on public.meeting_files (storage_path);

insert into storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
values (
  'meeting-files',
  'meeting-files',
  false,
  524288000,
  array['audio/*', 'video/*']::text[]
)
on conflict (id) do update
set
  name = excluded.name,
  public = false,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

-- The metadata row must exist before upload. Its existing RLS policy verifies
-- that the caller owns the referenced meeting; storage_path uniquely binds the
-- private object to that authorized meeting record.
create policy meeting_files_storage_select_own
  on storage.objects for select to authenticated
  using (
    bucket_id = 'meeting-files'
    and exists (
      select 1
      from public.meeting_files
      join public.meetings
        on meetings.id = meeting_files.meeting_id
      where meeting_files.storage_path = storage.objects.name
        and meetings.owner_id = (select auth.uid())
    )
  );

create policy meeting_files_storage_insert_own
  on storage.objects for insert to authenticated
  with check (
    bucket_id = 'meeting-files'
    and exists (
      select 1
      from public.meeting_files
      join public.meetings
        on meetings.id = meeting_files.meeting_id
      where meeting_files.storage_path = storage.objects.name
        and meetings.owner_id = (select auth.uid())
    )
  );

create policy meeting_files_storage_update_own
  on storage.objects for update to authenticated
  using (
    bucket_id = 'meeting-files'
    and exists (
      select 1
      from public.meeting_files
      join public.meetings
        on meetings.id = meeting_files.meeting_id
      where meeting_files.storage_path = storage.objects.name
        and meetings.owner_id = (select auth.uid())
    )
  )
  with check (
    bucket_id = 'meeting-files'
    and exists (
      select 1
      from public.meeting_files
      join public.meetings
        on meetings.id = meeting_files.meeting_id
      where meeting_files.storage_path = storage.objects.name
        and meetings.owner_id = (select auth.uid())
    )
  );

create policy meeting_files_storage_delete_own
  on storage.objects for delete to authenticated
  using (
    bucket_id = 'meeting-files'
    and exists (
      select 1
      from public.meeting_files
      join public.meetings
        on meetings.id = meeting_files.meeting_id
      where meeting_files.storage_path = storage.objects.name
        and meetings.owner_id = (select auth.uid())
    )
  );
