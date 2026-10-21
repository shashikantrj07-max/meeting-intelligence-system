# Planned Architecture

This document describes the current Phase 2 foundation and planned system
architecture. Meeting intelligence features and integrations noted as planned
are not yet implemented.

## Components

- **Frontend (`frontend/`)**: Next.js, React, TypeScript, Tailwind CSS, and
  shadcn/ui for the user interface. It communicates with the backend over HTTP
  and must not contain private API keys or privileged database credentials.
- **Backend (`backend/`)**: Python and FastAPI for API endpoints, validation,
  business logic, privileged database operations, file processing, AI
  orchestration, transcription, RAG, and export generation.
- **Database (`database/`)**: PostgreSQL stores relational application data.
  Phase 2 adds the initial schema migration and RLS ownership policies.
  pgvector and vector-search structures are planned for a later phase.
- **Authentication**: Supabase Auth is integrated in the frontend using
  `@supabase/ssr`. Frontend authentication uses only the public project URL and
  anon key. The service-role key is not used in this phase and must never be
  exposed to frontend code.
- **File storage**: Supabase Storage is a planned integration.

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
5. Future FastAPI endpoints will verify Supabase-issued access tokens on the
   backend. Frontend route protection alone must not be treated as authorization
   for backend resources.

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

The Phase 2 migration establishes the initial meeting schema; it does not
implement uploaded-file storage policies, a processing API, a vector extension,
or pgvector tables. Apply migrations and run their checks against a development
Supabase database as documented in `database/README.md`; a checked-in migration
is not evidence that it has been applied or validated against a live database.

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
AI summarization, media transcription, and background processing remain out
of scope.

## AI and processing boundaries

The backend will access AI through provider/service interfaces rather than
coupling application logic to one vendor. Gemini is planned as the primary LLM,
with Groq and local Ollama as interchangeable alternatives. Whisper is planned
for transcription, pyannote.audio for speaker diarization, and LangChain with
pgvector for RAG. None of these providers or processing integrations is
implemented yet.

## Planned request and data flow

1. The frontend sends user actions to FastAPI.
2. The backend validates requests, applies application logic, and coordinates
   database, storage, and provider interfaces.
3. PostgreSQL/pgvector stores structured records and embeddings; Supabase
   Storage holds uploaded media and generated artifacts.
4. The backend returns authorized results to the frontend for presentation and
   export.

## Planned deployment

The frontend is intended for Vercel, the backend for Render or Railway, and
PostgreSQL, authentication, and file storage for Supabase. Deployment
configuration is not part of the current phase.
