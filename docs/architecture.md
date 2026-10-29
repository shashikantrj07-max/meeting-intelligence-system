# Application Architecture

This document describes the implemented application architecture and remaining
planned integrations.

## Components

- **Frontend (`frontend/`)**: Next.js, React, TypeScript, and Tailwind CSS for
  the user interface. It uses Supabase under the signed-in session for
  owner-scoped browser operations and communicates with FastAPI for the
  implemented action-item, insight, and transcription operations. It must not
  contain private API keys or privileged database credentials.
- **Backend (`backend/`)**: Python and FastAPI for validated API operations,
  request-scoped Supabase access, transcription, meeting-insight generation,
  and action-item workflows. RAG and export generation are planned.
- **Database (`database/`)**: PostgreSQL stores relational application data.
  Migrations add the application schema and RLS ownership policies, including
  meeting insights and action-item history/review workflows. pgvector and
  vector-search structures are planned.
- **Authentication**: Supabase Auth is integrated in the frontend using
  `@supabase/ssr`. Frontend authentication uses only the public project URL and
  anon key. A service-role key must never be exposed to frontend code.
- **File storage**: meeting media is uploaded to a private Supabase Storage
  bucket, with access controlled by storage policies and meeting ownership.

## Authentication flow

1. The browser-side Supabase client handles email/password signup, login, and
   logout. Passwords are sent directly to Supabase Auth and are never stored by
   this application.
2. The Supabase SSR client stores and refreshes the session in cookies.
   The Next.js `src/proxy.ts` refreshes the session and redirects unauthenticated
   requests from `/dashboard` to `/login`; authenticated users visiting `/login`
   or `/signup` are redirected to `/dashboard`.
3. When email confirmation is enabled, Supabase returns the browser to
   `/auth/callback`. The route handler exchanges the one-time authorization code
   for a session and redirects to the dashboard.
4. The protected dashboard layout independently verifies the current user with
   Supabase on the server before rendering the application shell. The displayed
   email is informational; client-provided user IDs are not an authorization
   boundary.
5. The implemented FastAPI action-item, transcription, and meeting-insight
   routes verify Supabase-issued bearer access tokens and use a request-scoped
   Supabase client for their data operations. This verification is specific to
   those routes; do not assume every API endpoint implements the same checks.
   Frontend route protection alone must not be treated as authorization for
   backend resources.

Required browser configuration is `NEXT_PUBLIC_SUPABASE_URL` and
`NEXT_PUBLIC_SUPABASE_ANON_KEY`, stored locally in `frontend/.env.local`.
Private keys such as `SUPABASE_SERVICE_ROLE_KEY` must never use a
`NEXT_PUBLIC_` variable or be included in frontend code.

## Phase 2 database foundation

The additive migration in `database/migrations/` creates `profiles`,
`meetings`, `meeting_participants`, `meeting_files`, and `meeting_processing`.
Profiles are linked to Supabase Auth users. A database trigger creates a
profile on signup, and a non-overwriting backfill covers users that already
exist when the migration is applied.

RLS is enabled for all five tables. A user's profile and meetings are restricted
to that Auth user; access to participants, file metadata, and processing state
is inherited through the owning meeting. Database foreign keys cascade meeting
deletion to its child rows. SQL verification scripts are in
`database/tests/`, and the corresponding application types are maintained in
`frontend/src/types/database.ts`.

The Phase 2 migration establishes the initial meeting schema; later migrations
add uploaded-file storage policies and processing support. A vector extension
and pgvector tables are not implemented. Apply migrations and run their checks
against a development Supabase database as documented in `database/README.md`;
a checked-in migration is not evidence that it has been applied or validated
against a live database.

## Phase 4 transcript management

`public.meeting_transcripts` stores at most one transcript for each meeting.
The transcript has its own ID and timestamps and is deleted when its parent
meeting is deleted. Its RLS policies check ownership through the referenced
meeting, matching the existing participant, file, and processing policy
pattern. Authenticated browser operations cannot set an owner; only the
meeting relationship is supplied, and the database enforces access.

The meeting detail route loads transcript content only after the parent
meeting is visible under RLS. Transcript creation, editing, and deletion use
the normal Supabase browser client under the current authenticated session.
Transcript-based insights, media transcription, and background processing
were added in later phases.

## Phase 9F action-item history

`public.meeting_action_item_history` stores append-only snapshots of status,
owner, due-date, and priority changes. A database trigger records each field
transition only when its value changes, with a database-generated timestamp.
History reads are restricted by RLS through ownership of the related meeting;
authenticated clients receive read-only table access. The FastAPI history
endpoint also verifies the meeting and action item under the request's
authenticated Supabase client before returning the records.

## Phase 9G history-driven accountability signals

The paginated action-item accountability function derives `reopened`,
`repeated_updates`, `stale`, and `recent_activity` from the Phase 9F history
table and current tracked status. `recent_activity` means a recorded history
change within the last seven database days; `stale` means an item with at least
one history entry that is currently unresolved. Signal filters use the existing
accountability endpoint and preserve its dashboard URL and pagination
conventions. The history endpoint returns these same database-computed signals
alongside the history records so the action-item view can present both together.

## Phase 9H signal review workflow

`public.meeting_action_item_signal_reviews` stores the latest review watermark
for an action item with accountability signals. The authenticated dashboard
offers a "Needs review" queue; marking an item reviewed stores the newest
history timestamp and a database-generated review timestamp. A later tracked
field change advances history beyond that watermark and returns the item to the
queue. RLS permits only meeting owners to read review state, and direct client
writes are denied. A narrowly scoped RPC performs review writes after checking
the authenticated meeting owner and action item because it must atomically
derive the watermark from history without accepting a client timestamp.

## Phase 9I accountability review analytics

The authenticated `GET /api/meetings/action-items/review-analytics` endpoint
returns reviewable, acknowledged, currently needing-review, and reopened-since-
review item counts plus one-decimal review coverage. The database derives these
values from current Phase 9G signals, Phase 9F history timestamps, and the Phase
9H review watermark; it does not persist redundant analytics state.
`Reopened since review` means an item has a review watermark and newer meaningful
history, not the Phase 9G status-reopened signal. Acknowledgement does not change
action-item status. The read-only `SECURITY INVOKER` RPC scopes items through
`auth.uid()` meeting ownership and relies on existing RLS for history and review
rows. Migration: `20261027000400_phase9i_action_item_review_analytics.sql`.

## Phase 9J review analytics drilldown

The review analytics count metrics link into the existing paginated
accountability queue. Its `review_state` filter supports `all`, `reviewable`,
`reviewed`, `needs_review`, and `reopened_since_review`, and composes with the
existing status/accountability filter and page offset. The database RPC derives
these states from current accountability signals, the history timestamp, and
the Phase 9H review watermark; it does not infer review state in the browser.
`Mark reviewed` uses the existing review RPC and refreshes the dashboard, so an
acknowledged item leaves the needs-review result and analytics recalculate.
Later meaningful history activity remains newer than the stored watermark and
returns the item to needs review. Migration:
`20261027000500_phase9j_action_item_review_drilldown.sql`.

## AI and processing boundaries

The backend generates meeting insights from transcripts through its current
Gemini-backed provider implementation. Audio/video transcription and processing
status are implemented. Additional interchangeable AI providers, local
inference, speaker diarization, and RAG with pgvector remain planned.

## Request and data flow

1. The frontend sends user actions to FastAPI.
2. FastAPI verifies bearer tokens on the implemented action-item, transcription,
   and meeting-insight routes, validates their inputs, and uses a
   request-scoped Supabase client for authorized data operations.
3. Browser-side meeting, transcript, and file operations use the signed-in
   Supabase session and are constrained by database and storage RLS policies.
4. PostgreSQL stores structured meeting data and Supabase Storage holds
   uploaded media. The frontend presents returned results; RAG and exports are
   not implemented.

## Planned deployment

The frontend is intended for Vercel, the backend for Render or Railway, and
PostgreSQL, authentication, and file storage for Supabase. Deployment
configuration is not part of the current phase.
