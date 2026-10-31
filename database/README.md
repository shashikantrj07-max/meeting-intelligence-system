# Database

The database uses PostgreSQL through Supabase. Its migrations define profiles,
meetings, participants, files, processing state, transcripts, generated meeting
insights, tracked action items, action-item history, accountability signals,
and signal-review state, with ownership constraints, indexes, triggers, and
row-level security (RLS) policies. Meeting-content search uses PostgreSQL
full-text and trigram indexes; vector search and pgvector structures remain
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
- `search_my_meetings`: authenticated, owner-scoped title and transcript search
  with bounded results and short transcript context snippets.
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

## Fresh development database setup

Use a disposable local Supabase/PostgreSQL project or a dedicated development
project. The Phase 2 migration expects Supabase Auth objects; Phase 6 expects
Supabase Storage objects. A plain PostgreSQL database without the Supabase
`auth` and `storage` schemas is not sufficient. Review and back up a shared
database before applying schema changes.

The migrations require PostgreSQL 13 or newer. Phase 10 also requires the
`pg_trgm` extension. Its migration creates the `extensions` schema and asks
PostgreSQL to install `pg_trgm` there, then resolves the trigram operator class
through `pg_catalog`, `public`, and `extensions`. `CREATE EXTENSION IF NOT
EXISTS` does not relocate an extension that is already installed elsewhere;
before applying Phase 10 to an existing project, confirm that `pg_trgm` is
available in `public` or `extensions`. If it is installed in another schema,
review and adapt the migration deliberately rather than moving a production
extension as part of this change.

The migration files are ordered schema changes and are not all rerunnable.
First confirm that the target is a fresh database. For an existing database,
inspect its migration state and schema before deciding what, if anything, is
missing; do not blindly replay this list. Apply each migration once, from the
repository root, in this order:

1. `20261021000100_phase2_database_foundation.sql`
2. `20261022000100_phase4_meeting_transcripts.sql`
3. `20261022000100_phase5_meeting_insights.sql`
4. `20261022000200_phase6_meeting_file_storage.sql`
5. `20261022000300_phase6a_structured_meeting_insights.sql`
6. `20261025000100_phase8_meeting_action_items.sql`
7. `20261025000200_phase9a_accountability_summary.sql`
8. `20261025000300_phase9a_accountability_date_safety.sql`
9. `20261025000400_phase9b_accountability_drilldown.sql`
10. `20261025000500_phase9c_action_item_prioritization.sql`
11. `20261025000600_phase9d_action_item_followup.sql`
12. `20261027000100_phase9f_action_item_history.sql`
13. `20261027000200_phase9g_action_item_accountability_signals.sql`
14. `20261027000300_phase9h_action_item_signal_review.sql`
15. `20261027000400_phase9i_action_item_review_analytics.sql`
16. `20261027000500_phase9j_action_item_review_drilldown.sql`
17. `20261028000100_phase10_meeting_content_search.sql`
18. `20261030000100_phase11_durable_processing_jobs.sql`
19. `20261031000100_phase11_claim_job_meeting_id_ambiguity.sql`

There is no Phase 9E SQL migration in this repository; Phase 9F–9J depend on
the tracked-action-item schema and accountability functions from the preceding
listed migrations. The migration connection needs the privileges used by the
scripts, including creating objects in the Supabase `auth` and `storage`
schemas and policies.

Before connecting, confirm the intended development/test project using trusted
project records or the Supabase dashboard. Check its project identity against
the known development project; do not proceed if you cannot distinguish it
from production. Do not rely on a connection URL alone as proof that the
target is safe.

`DATABASE_URL` must be available in the same PowerShell process that launches
`psql`. Obtain the connection settings through your trusted local
secret-management process. This repository does not prescribe how to load
them into PowerShell; that step is operator-dependent. Do not copy the value
into source files, documentation, shared terminal transcripts, or commands
that you save or share.

You can check whether the variable is set without displaying its value:

```powershell
if ([string]::IsNullOrWhiteSpace($env:DATABASE_URL)) { "DATABASE_URL is not set." } else { "DATABASE_URL is set; value not displayed." }
```

The project documents PostgreSQL's `psql` client. Check its local
availability with `psql --version`; this reports the client version only and
does not identify or confirm the database target.

After confirming the development/test target and making `DATABASE_URL`
available in this PowerShell process, this is the documented `psql`
invocation form. **This example connects to the database; do not run it until
the target has been confirmed.**

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1
```

The migration loop below is for applying migrations, not for discovering
database state. Do not run it against an existing database until its migration
state has been established and any missing migrations have been deliberately
identified.

This repository has no confirmed migration ledger or documented tracking
mechanism. Migration filenames show the intended order, but do not establish
which migrations have been applied. Do not replay migrations blindly against
an existing database. If no authoritative deployment record is available,
later obtain explicit authorization to inspect the confirmed development
database's schema and catalog read-only; that can verify expected objects but
may not prove which migration file created them.

The following loop applies the listed migrations in order and stops when a
command fails. Use it only for a confirmed fresh database, not as a preflight
or migration-state check:

```powershell
$migrations = @(
  "database/migrations/20261021000100_phase2_database_foundation.sql",
  "database/migrations/20261022000100_phase4_meeting_transcripts.sql",
  "database/migrations/20261022000100_phase5_meeting_insights.sql",
  "database/migrations/20261022000200_phase6_meeting_file_storage.sql",
  "database/migrations/20261022000300_phase6a_structured_meeting_insights.sql",
  "database/migrations/20261025000100_phase8_meeting_action_items.sql",
  "database/migrations/20261025000200_phase9a_accountability_summary.sql",
  "database/migrations/20261025000300_phase9a_accountability_date_safety.sql",
  "database/migrations/20261025000400_phase9b_accountability_drilldown.sql",
  "database/migrations/20261025000500_phase9c_action_item_prioritization.sql",
  "database/migrations/20261025000600_phase9d_action_item_followup.sql",
  "database/migrations/20261027000100_phase9f_action_item_history.sql",
  "database/migrations/20261027000200_phase9g_action_item_accountability_signals.sql",
  "database/migrations/20261027000300_phase9h_action_item_signal_review.sql",
  "database/migrations/20261027000400_phase9i_action_item_review_analytics.sql",
  "database/migrations/20261027000500_phase9j_action_item_review_drilldown.sql",
  "database/migrations/20261028000100_phase10_meeting_content_search.sql",
  "database/migrations/20261030000100_phase11_durable_processing_jobs.sql"
)
foreach ($migration in $migrations) {
  psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f $migration
  if ($LASTEXITCODE -ne 0) { throw "Migration failed: $migration" }
}
```

`-1` wraps each migration in a transaction. The loop applies the complete list;
do not use it against a database where any listed migration may already have
been applied.

For an existing development database with all preceding migrations already
applied, first verify its project identity and migration state. Then apply only
the new migration:

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -1 `
  -f database/migrations/20261028000100_phase10_meeting_content_search.sql
```

Do not use a production connection. This migration adds the `pg_trgm`
extension if needed, two indexes, a generated transcript search vector, and an
authenticated search RPC; it is not safe to replay blindly.

### Phase 11 durable processing jobs

`20261030000100_phase11_durable_processing_jobs.sql` depends on the existing
meetings, processing, transcript, file, insight, and tracked-action-item
schema. It adds a durable job table, owner-scoped idempotent enqueueing,
atomic worker claims, expiring leases, fenced output persistence, and
retry/failure transitions. The follow-up migration
`20261031000100_phase11_claim_job_meeting_id_ambiguity.sql` replaces the claim
RPC to resolve the ambiguous `meeting_id` conflict target caused by the
function's output column and the `meeting_processing` table column. Apply the
migrations in timestamp order, only after verifying the development project
identity and confirming that prerequisite migrations have been applied. This
repository does not establish a live migration ledger.

For an existing development database where Phase 11 is already applied and
only the corrective migration is pending, apply only that corrective
migration after verifying the target and migration state:

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -1 `
  -f database/migrations/20261031000100_phase11_claim_job_meeting_id_ambiguity.sql
```

The Phase 11 and corrective migrations are reported as applied in the local
demo project. Live demo verification confirmed that the worker claimed and
processed a job, generated insights and action items appeared on the dashboard,
and completed results remained visible after refresh. This records the
reported local demo result; it is not a migration ledger or a production
readiness claim. Do not replay either migration blindly. After applying them,
review and run
`database/tests/verify_phase11_durable_processing_jobs.sql` only against a
disposable test database with two existing test users and the required
database privileges; the script inserts fixture rows inside a transaction
and rolls them back. The catalog-only corrective check is
`database/tests/verify_phase11_claim_job_ambiguity_fix.sql` and is read-only.

## Verification scripts

The scripts below do not apply migrations. Separate read-only schema/catalog
checks from behavioral tests that perform database operations.

### Read-only schema/catalog checks

These scripts inspect database catalogs and assert schema, policy, privilege,
RPC, or Storage configuration. They do not intentionally write application
data:

1. `verify_schema.sql`
2. `verify_phase4_transcripts.sql`
3. `verify_phase5_meeting_insights.sql`
4. `verify_phase6_meeting_file_storage.sql`
5. `verify_phase9f_action_item_history.sql`
6. `verify_phase9g_action_item_accountability_signals.sql`
7. `verify_phase9h_action_item_signal_review.sql`
8. `verify_phase9i_action_item_review_analytics.sql`
9. `verify_phase9j_action_item_review_drilldown.sql`

Run them only against the confirmed development/test database, after verifying
that their required migration prerequisites are present. They require a
database connection and therefore are not offline checks.

`verify_phase10_meeting_content_search.sql` is a behavioral test rather than a
read-only catalog check. It uses two existing test users, inserts fixture
meetings/transcript content inside a transaction, checks search behavior and
owner isolation, and rolls all fixture rows back. Run it only against a
disposable development/test project with two existing users who have profiles:

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 `
  -v user_a="EXISTING_TEST_USER_A_UUID" `
  -v user_b="EXISTING_TEST_USER_B_UUID" `
  -f database/tests/verify_phase10_meeting_content_search.sql
```

Confirm the database identity before setting `DATABASE_URL`; do not use real
user UUIDs in shared logs or reports.

The Phase 9G and 9H scripts assert contracts from the final Phase 9F–9J schema,
including the three-argument accountability RPC installed by Phase 9J. They
are not standalone checks for an intermediate 9G or 9H schema. This repository
does not currently include verification scripts for Phase 6A, Phase 8, or
Phases 9A–9D; absence of a script is not evidence that a migration was applied
or verified.

Run the catalog/schema checks after the migration sequence:

```powershell
$catalogScripts = @(
  "database/tests/verify_schema.sql",
  "database/tests/verify_phase4_transcripts.sql",
  "database/tests/verify_phase5_meeting_insights.sql",
  "database/tests/verify_phase6_meeting_file_storage.sql",
  "database/tests/verify_phase9f_action_item_history.sql",
  "database/tests/verify_phase9g_action_item_accountability_signals.sql",
  "database/tests/verify_phase9h_action_item_signal_review.sql",
  "database/tests/verify_phase9i_action_item_review_analytics.sql",
  "database/tests/verify_phase9j_action_item_review_drilldown.sql"
)
foreach ($script in $catalogScripts) {
  psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f $script
  if ($LASTEXITCODE -ne 0) { throw "Verification failed: $script" }
}
```

### Behavioral RLS test

`verify_phase2_rls.sql` is not a read-only catalog check. It performs temporary
inserts, updates, and deletes inside a transaction, then rolls them back. Run
it only against a disposable test database, never production or a shared
development database. It requires two distinct existing Supabase Auth users
whose profile rows exist, and a connection allowed to inspect `auth.users`
and `SET ROLE authenticated`.

The Phase 6 migration creates the private `meeting-files` bucket with a 500 MiB
maximum object size and audio/video MIME types only. Storage object SELECT,
INSERT, UPDATE, and DELETE policies require an exact `storage_path` match to a
`meeting_files` row whose parent meeting has `owner_id = auth.uid()`. The
existing `meeting_files` table RLS also applies. Create the authorized metadata
row before uploading the object; do not accept an owner ID from the client.

The script requires the UUIDs of two different existing Supabase Auth users.
Supply them using the documented `psql` variables below only when running the
behavioral test on a disposable database; do not include actual UUIDs in
documentation or shared terminal transcripts.

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -v user_a="<USER_A_UUID>" -v user_b="<USER_B_UUID>" -f database/tests/verify_phase2_rls.sql
```

The script connection must be able to `SET ROLE authenticated` and inspect
`auth.users` before that role switch. Never use production users or a production
database for this verification.

`frontend/src/types/database.ts` contains manually maintained Supabase client
types for the current public tables. Regenerate or reconcile these types when
the schema changes; do not assume they have been generated from a live database.
