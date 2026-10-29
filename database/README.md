# Database

The database uses PostgreSQL through Supabase. Its migrations define profiles,
meetings, participants, files, processing state, transcripts, generated meeting
insights, tracked action items, action-item history, accountability signals,
and signal-review state, with ownership constraints, indexes, triggers, and
row-level security (RLS) policies. Vector search and pgvector structures are
planned.

## Schema

- `profiles`: one profile per `auth.users` row. A trigger creates profiles for
  new Auth users, and the migration backfills existing users without replacing
  existing profile data.
- `meetings`: user-owned meeting metadata and lifecycle status.
- `meeting_participants`: participants associated with a meeting.
- `meeting_files`: metadata and storage path for a meeting file. File storage
  is stored in the private Supabase Storage bucket `meeting-files`. Storage
  object policies require an owner-authorized `meeting_files` metadata row.
- `meeting_processing`: one processing-state record per meeting, used to track
  transcription and insight-generation progress.
- `meeting_transcripts`: one editable transcript per meeting, associated
  directly with the parent meeting.
- `meeting_insights` and `meeting_action_items`: generated meeting insights
  and their tracked action items.
- `meeting_action_item_history` and `meeting_action_item_signal_reviews`:
  action-item change history and review state. Accountability signals are
  calculated by database functions rather than stored as duplicate state.

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

## Phase 9F–9J action-item history and review

These migrations extend the Phase 8 `meeting_action_items` table and the
Phase 9A–9E accountability schema. Apply those prerequisites first, in their
documented chronological order. In particular, Phase 9F depends on the
Phase 8 action-item table, and the later phases extend the history, signal,
review, and accountability RPCs created by the preceding phases.

Before applying any migration, inspect the target database's actual schema
objects and confirm which changes are already present. Do not rely on a
migration-history table being available, and do not rerun a migration whose
objects are already installed. These migration files are ordered schema
changes, not a substitute for checking database state.

From the repository root in PowerShell, apply only migrations confirmed to be
missing, in this order:

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f database/migrations/20261027000100_phase9f_action_item_history.sql
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f database/migrations/20261027000200_phase9g_action_item_accountability_signals.sql
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f database/migrations/20261027000300_phase9h_action_item_signal_review.sql
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f database/migrations/20261027000400_phase9i_action_item_review_analytics.sql
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f database/migrations/20261027000500_phase9j_action_item_review_drilldown.sql
```

`-1` runs each migration in a transaction, and `ON_ERROR_STOP=1` stops `psql`
when a statement fails. The connection must have the database privileges
required by the migration. Keep the connection string in the environment;
never put it in a command, source file, or frontend configuration.

After all required Phase 9F–9J migrations have been applied, run the matching
verification scripts from the repository root in this order:

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f database/tests/verify_phase9f_action_item_history.sql
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f database/tests/verify_phase9g_action_item_accountability_signals.sql
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f database/tests/verify_phase9h_action_item_signal_review.sql
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f database/tests/verify_phase9i_action_item_review_analytics.sql
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f database/tests/verify_phase9j_action_item_review_drilldown.sql
```

The Phase 9G and 9H verification scripts check the final Phase 9F–9J
accountability RPC contract, including the three-argument
`get_my_action_item_accountability_items(text, integer, text)` function
introduced by Phase 9J. Therefore, run those scripts only after all of the
required Phase 9F–9J migrations are present; they are not standalone checks
for an intermediate Phase 9G or 9H schema. These scripts make catalog and
privilege assertions; they do not apply migrations.

`frontend/src/types/database.ts` contains manually maintained Supabase client
types for the current public tables. Regenerate or reconcile these types when
the schema changes; do not assume they have been generated from a live database.
