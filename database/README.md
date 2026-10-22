# Database

The database foundation uses PostgreSQL through Supabase. The migrations create
the application profile, meeting metadata, and one-to-one meeting transcript
tables with ownership constraints, indexes, timestamp triggers, and row-level
security (RLS) policies. AI-generated meeting content, embeddings, and
pgvector structures belong to later phases.

## Schema

- `profiles`: one profile per `auth.users` row. A trigger creates profiles for
  new Auth users, and the migration backfills existing users without replacing
  existing profile data.
- `meetings`: user-owned meeting metadata and lifecycle status.
- `meeting_participants`: participants associated with a meeting.
- `meeting_files`: metadata and storage path for a meeting file. File storage
  is stored in the private Supabase Storage bucket `meeting-files`. Storage
  object policies require an owner-authorized `meeting_files` metadata row.
- `meeting_processing`: one processing-state record per meeting; processing
  functionality is not implemented yet.
- `meeting_transcripts`: one editable transcript per meeting, associated
  directly with the parent meeting.

Every application table has RLS enabled. Policies restrict profiles and
meetings to their owner; child rows, including transcripts, inherit access
through the referenced meeting. Authenticated users do not receive `DELETE`
permission for profiles or processing records. Meeting deletion cascades to
its participants, files, processing record, and transcript.

## Apply the migration

Use a disposable local Supabase/PostgreSQL project or a development project.
Review and back up a shared database before applying schema changes. Do not
commit database credentials or place them in frontend environment variables.

From the repository root, apply the migration with `psql`:

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f database/migrations/20261021000100_phase2_database_foundation.sql
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f database/migrations/20261022000100_phase4_meeting_transcripts.sql
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f database/migrations/20261022000200_phase6_meeting_file_storage.sql
```

`-1` wraps the migration in one transaction. The connection needs permission to
create the tables, functions, triggers, policies, and Auth trigger in the
Supabase `auth` schema. For local Supabase development, use its database
connection string; do not substitute the frontend anon key.

## Verification

After applying the migration, run the catalog/schema assertions:

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f database/tests/verify_schema.sql
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f database/tests/verify_phase4_transcripts.sql
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f database/tests/verify_phase6_meeting_file_storage.sql
```

The Phase 6 migration creates the private `meeting-files` bucket with a 500 MiB
maximum object size and audio/video MIME types only. Storage object SELECT,
INSERT, UPDATE, and DELETE policies require an exact `storage_path` match to a
`meeting_files` row whose parent meeting has `owner_id = auth.uid()`. The
existing `meeting_files` table RLS also applies. Create the authorized metadata
row before uploading the object; do not accept an owner ID from the client.

The ownership behavior script needs two different, existing Supabase Auth
users whose profile rows were created by the migration's trigger or backfill.
Run it only against a disposable development/test database; it creates meeting
test rows in a transaction and rolls them back.

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -v user_a="<USER_A_UUID>" -v user_b="<USER_B_UUID>" -f database/tests/verify_phase2_rls.sql
```

The script connection must be able to `SET ROLE authenticated` and inspect
`auth.users` before that role switch. Never use production users or a production
database for this verification.

`frontend/src/types/database.ts` contains manually maintained Supabase client
types for the current public tables. Regenerate or reconcile these types when
the schema changes; do not assume they have been generated from a live database.
