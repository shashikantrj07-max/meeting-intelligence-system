-- Phase 2 database foundation.
-- All application data is owned by auth.users through profiles and meetings.

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  avatar_url text,
  created_at timestamptz not null default pg_catalog.now(),
  updated_at timestamptz not null default pg_catalog.now()
);

create table public.meetings (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete cascade,
  title text not null,
  description text,
  status text not null default 'draft',
  meeting_date timestamptz,
  duration_seconds integer,
  created_at timestamptz not null default pg_catalog.now(),
  updated_at timestamptz not null default pg_catalog.now(),
  constraint meetings_title_not_blank check (pg_catalog.btrim(title) <> ''),
  constraint meetings_duration_nonnegative check (
    duration_seconds is null or duration_seconds >= 0
  ),
  constraint meetings_status_valid check (
    status in ('draft', 'processing', 'completed', 'failed')
  )
);

create table public.meeting_participants (
  id uuid primary key default gen_random_uuid(),
  meeting_id uuid not null references public.meetings (id) on delete cascade,
  name text not null,
  email text,
  role text,
  created_at timestamptz not null default pg_catalog.now(),
  constraint meeting_participants_name_not_blank check (
    pg_catalog.btrim(name) <> ''
  )
);

create table public.meeting_files (
  id uuid primary key default gen_random_uuid(),
  meeting_id uuid not null references public.meetings (id) on delete cascade,
  storage_path text not null,
  original_filename text not null,
  mime_type text,
  file_size_bytes bigint,
  created_at timestamptz not null default pg_catalog.now(),
  constraint meeting_files_storage_path_not_blank check (
    pg_catalog.btrim(storage_path) <> ''
  ),
  constraint meeting_files_filename_not_blank check (
    pg_catalog.btrim(original_filename) <> ''
  ),
  constraint meeting_files_size_nonnegative check (
    file_size_bytes is null or file_size_bytes >= 0
  )
);

create table public.meeting_processing (
  id uuid primary key default gen_random_uuid(),
  meeting_id uuid not null unique references public.meetings (id) on delete cascade,
  stage text not null default 'pending',
  error_message text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default pg_catalog.now(),
  updated_at timestamptz not null default pg_catalog.now(),
  constraint meeting_processing_stage_valid check (
    stage in ('pending', 'transcribing', 'analyzing', 'completed', 'failed')
  )
);

create index meetings_owner_id_idx on public.meetings (owner_id);
create index meetings_owner_created_at_idx
  on public.meetings (owner_id, created_at desc);
create index meeting_participants_meeting_id_idx
  on public.meeting_participants (meeting_id);
create index meeting_files_meeting_id_idx
  on public.meeting_files (meeting_id);
-- meeting_processing_meeting_id_key provides the meeting_id lookup index.

alter table public.profiles enable row level security;
alter table public.meetings enable row level security;
alter table public.meeting_participants enable row level security;
alter table public.meeting_files enable row level security;
alter table public.meeting_processing enable row level security;

revoke all on table public.profiles from public, anon, authenticated;
revoke all on table public.meetings from public, anon, authenticated;
revoke all on table public.meeting_participants from public, anon, authenticated;
revoke all on table public.meeting_files from public, anon, authenticated;
revoke all on table public.meeting_processing from public, anon, authenticated;

grant select, insert, update on table public.profiles to authenticated;
grant select, insert, update, delete on table public.meetings to authenticated;
grant select, insert, update, delete
  on table public.meeting_participants to authenticated;
grant select, insert, update, delete on table public.meeting_files to authenticated;
grant select, insert, update on table public.meeting_processing to authenticated;

create policy profiles_select_own
  on public.profiles for select to authenticated
  using (id = (select auth.uid()));
create policy profiles_insert_own
  on public.profiles for insert to authenticated
  with check (id = (select auth.uid()));
create policy profiles_update_own
  on public.profiles for update to authenticated
  using (id = (select auth.uid()))
  with check (id = (select auth.uid()));

create policy meetings_select_own
  on public.meetings for select to authenticated
  using (owner_id = (select auth.uid()));
create policy meetings_insert_own
  on public.meetings for insert to authenticated
  with check (owner_id = (select auth.uid()));
create policy meetings_update_own
  on public.meetings for update to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));
create policy meetings_delete_own
  on public.meetings for delete to authenticated
  using (owner_id = (select auth.uid()));

create policy meeting_participants_select_own
  on public.meeting_participants for select to authenticated
  using (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_participants.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );
create policy meeting_participants_insert_own
  on public.meeting_participants for insert to authenticated
  with check (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_participants.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );
create policy meeting_participants_update_own
  on public.meeting_participants for update to authenticated
  using (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_participants.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_participants.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );
create policy meeting_participants_delete_own
  on public.meeting_participants for delete to authenticated
  using (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_participants.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );

create policy meeting_files_select_own
  on public.meeting_files for select to authenticated
  using (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_files.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );
create policy meeting_files_insert_own
  on public.meeting_files for insert to authenticated
  with check (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_files.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );
create policy meeting_files_update_own
  on public.meeting_files for update to authenticated
  using (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_files.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_files.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );
create policy meeting_files_delete_own
  on public.meeting_files for delete to authenticated
  using (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_files.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );

create policy meeting_processing_select_own
  on public.meeting_processing for select to authenticated
  using (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_processing.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );
create policy meeting_processing_insert_own
  on public.meeting_processing for insert to authenticated
  with check (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_processing.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );
create policy meeting_processing_update_own
  on public.meeting_processing for update to authenticated
  using (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_processing.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.meetings
      where meetings.id = meeting_processing.meeting_id
        and meetings.owner_id = (select auth.uid())
    )
  );

-- The trigger runs as the table owner, never copies credentials, and catches
-- profile-only failures so they cannot abort creation of an auth.users row.
create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name)
  values (
    new.id,
    nullif(pg_catalog.btrim(new.raw_user_meta_data ->> 'display_name'), '')
  )
  on conflict (id) do nothing;

  return new;
exception
  when others then
    raise warning 'Profile creation failed for auth user %: %', new.id, sqlerrm;
    return new;
end;
$$;

revoke all on function public.handle_new_auth_user() from public, anon, authenticated;

-- Backfill profiles for users who signed up before this migration.
insert into public.profiles (id, display_name)
select
  users.id,
  nullif(pg_catalog.btrim(users.raw_user_meta_data ->> 'display_name'), '')
from auth.users as users
on conflict (id) do nothing;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_auth_user();

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = pg_catalog.now();
  return new;
end;
$$;

revoke all on function public.set_updated_at() from public, anon, authenticated;

create trigger profiles_set_updated_at
  before update on public.profiles
  for each row execute function public.set_updated_at();
create trigger meetings_set_updated_at
  before update on public.meetings
  for each row execute function public.set_updated_at();
create trigger meeting_processing_set_updated_at
  before update on public.meeting_processing
  for each row execute function public.set_updated_at();
