# Database

The Phase 2 foundation uses PostgreSQL through Supabase. The initial migration
creates the application profile and meeting metadata tables, ownership
constraints, indexes, timestamp triggers, and row-level security (RLS)
policies. It does not create meeting-content, transcription, embedding, or
pgvector structures; those belong to later phases.

## Schema

- `profiles`: one profile per `auth.users` row. A trigger creates profiles for
  new Auth users, and the migration backfills existing users without replacing
  existing profile data.
- `meetings`: user-owned meeting metadata and lifecycle status.
- `meeting_participants`: participants associated with a meeting.
- `meeting_files`: metadata and storage path for a meeting file. File storage
  itself is not configured by this migration.
- `meeting_processing`: one processing-state record per meeting; processing
  functionality is not implemented yet.

Every application table has RLS enabled. Policies restrict profiles and
meetings to their owner; child rows inherit access through the referenced
meeting. Authenticated users do not receive `DELETE` permission for profiles
or processing records. Meeting deletion cascades to its participants, files,
and processing record.

## Apply the migration

Use a disposable local Supabase/PostgreSQL project or a development project.
Review and back up a shared database before applying schema changes. Do not
commit database credentials or place them in frontend environment variables.

From the repository root, apply the migration with `psql`:

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f database/migrations/20261021000100_phase2_database_foundation.sql
```

`-1` wraps the migration in one transaction. The connection needs permission to
create the tables, functions, triggers, policies, and Auth trigger in the
Supabase `auth` schema. For local Supabase development, use its database
connection string; do not substitute the frontend anon key.

## Verification

After applying the migration, run the catalog/schema assertions:

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f database/tests/verify_schema.sql
```

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
