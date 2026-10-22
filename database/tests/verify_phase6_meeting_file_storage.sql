-- Run after applying 20261022000200_phase6_meeting_file_storage.sql.

do $$
begin
  if not exists (
    select 1
    from storage.buckets
    where id = 'meeting-files'
      and name = 'meeting-files'
      and public = false
      and file_size_limit = 524288000
      and allowed_mime_types = array['audio/*', 'video/*']::text[]
  ) then
    raise exception 'Private meeting-files bucket configuration is incorrect';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_indexes
    where schemaname = 'public'
      and tablename = 'meeting_files'
      and indexname = 'meeting_files_storage_path_key'
      and indexdef ilike '%unique%'
  ) then
    raise exception 'Unique meeting_files.storage_path index is missing';
  end if;

  if (
    select count(*)
    from pg_catalog.pg_policies
    where schemaname = 'storage'
      and tablename = 'objects'
      and policyname in (
        'meeting_files_storage_select_own',
        'meeting_files_storage_insert_own',
        'meeting_files_storage_update_own',
        'meeting_files_storage_delete_own'
      )
      and 'authenticated' = any(roles)
  ) <> 4 then
    raise exception 'Expected all four authenticated meeting file Storage policies';
  end if;
end;
$$;
