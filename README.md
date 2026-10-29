# Meeting Intelligence System

A meeting workspace for managing meetings, storing transcripts, generating
structured meeting intelligence, and following up on tracked action items.
Implemented capabilities include Supabase authentication, owner-scoped meeting
and transcript data, media upload and transcription, meeting insights, and the
Phase 9 action-item accountability and review workflow.

## Implemented functionality

- **Authentication and meeting workspace:** Supabase email/password
  authentication, server-verified protection for authenticated pages, and
  create, view, edit, and delete operations for a user's meetings.
- **Transcripts and meeting intelligence:** create and edit transcripts,
  upload meeting audio/video to the private Supabase Storage bucket, request
  transcription, and generate a meeting summary and structured insights from a
  transcript. Processing state is available in the meeting workspace.
- **Tracked action items:** track status, owner, due date, and priority;
  review changes in action-item history; and view database-derived follow-up
  classifications and accountability signals.
- **Signal review and analytics:** acknowledge action-item signals, see review
  coverage and related counts, and filter/paginate the action-item drilldown by
  accountability and review state.
- **Database ownership controls:** migrations define row-level security for
  meeting-owned data and restricted access to action-item history and review
  state. The API routes that handle action-item, transcription, and insight
  requests verify Supabase bearer tokens; this does not imply that every API
  route in the repository has the same authentication behavior.

Migrations and tests are source files, not proof that a particular database has
been migrated. Apply them to a development database and run the matching
verification scripts as described in [database/README.md](database/README.md).

## Planned functionality

- Search across transcript and meeting content (the dashboard currently
  supports meeting-title search).
- Retrieval-augmented chat, vector search, and pgvector.
- Export and reporting workflows.
- Additional interchangeable AI providers and local inference.
- Production deployment and operational hardening.

## Technology stack

- **Frontend:** Next.js, React, TypeScript, and Tailwind CSS
- **Backend:** Python, FastAPI
- **Database:** PostgreSQL through Supabase, with owner-scoped RLS; pgvector is
  planned
- **Authentication and file storage:** Supabase Auth and private Supabase
  Storage
- **AI and transcription:** meeting-insight generation and audio/video
  transcription are implemented; additional providers, diarization, and
  retrieval integrations are planned

## High-level architecture

The Next.js frontend and FastAPI backend are separate applications. The
frontend calls FastAPI over HTTP and uses only public Supabase configuration;
it does not contain private API keys or server-privileged credentials. The
backend verifies bearer tokens on the implemented action-item, transcription,
and insight routes and uses request-scoped Supabase access for their data
operations. RAG and exports remain planned.

See [docs/architecture.md](docs/architecture.md) for the architecture and
authentication flow, and [database/README.md](database/README.md) for migration
and verification instructions.

## Repository structure

```text
meeting-intelligence-system/
├── frontend/                  # Next.js + TypeScript + Tailwind application
├── backend/                   # FastAPI app, routes, and services
│   └── app/
├── database/                  # PostgreSQL migrations and verification scripts
│   ├── migrations/
│   └── tests/
├── docs/                      # Architecture documentation
├── .github/
│   └── copilot-instructions.md
├── .env.example               # Names/placeholders only; no real secrets
├── .gitignore
└── README.md
```

## Local setup

Requirements: Node.js with npm, and Python 3.12 (or another compatible Python
version). The frontend and backend can be installed and started independently.

### Environment variables

Create `frontend/.env.local` with only the Supabase project URL and anon key
from the Supabase project settings. These two `NEXT_PUBLIC_` values are public
client configuration; Supabase Auth applies its own access controls. Never put
a service-role key, database credential, or other private secret in frontend
code or a `NEXT_PUBLIC_` variable. `.env.local` and other `.env` files are
ignored by Git and must never be committed. The service-role key is not needed
by this phase.

```powershell
@'
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
'@ | Set-Content -Encoding ascii frontend\.env.local
```

Fill in the two values in `frontend/.env.local`. In Supabase Auth settings,
configure the local site URL as `http://localhost:3000` and allow
`http://localhost:3000/auth/callback` as a redirect URL. `.env.example`
documents the broader project configuration but should not be copied wholesale
into the frontend environment.

### Frontend setup

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. See [frontend/README.md](frontend/README.md) for
frontend-specific commands.

### Backend setup

From the repository root, create and activate a virtual environment and install
the backend dependencies:

```powershell
py -3.12 -m venv backend\.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

Run the API:

```powershell
cd backend
python -m uvicorn app.main:app --reload
```

The health check is available at `http://127.0.0.1:8000/health` and returns
`{"status":"ok"}`. See [backend/README.md](backend/README.md) for details.

### Database setup

Database migrations are not automatically applied by starting the frontend or
backend. Follow [database/README.md](database/README.md) to review, apply, and
verify migrations against a development database. The README does not certify
the migration state of any live or local database.

## Current project status

**Phase 1 — authentication and application shell:** Implemented. Supabase Auth
provides signup and password login; authenticated users can access the
protected dashboard, see their email, and log out.

**Phase 2 — database foundation:** Implemented, including owner-scoped RLS
policies and profile creation/backfill.

**Phase 3 — meeting management:** Implemented. Authenticated users can create,
view, edit, and delete their own meetings.

**Phase 4 — transcript management:** Transcript migration, ownership RLS,
manual TypeScript types, and authenticated create/view/edit/delete UI are
implemented.

**Phases 5–6 — meeting insights and media processing:** Structured meeting
insight generation from a transcript, audio/video file upload to private
storage, transcription requests, and processing status are implemented.

**Phase 8 and Phases 9A–9E — tracked action items:** Action items are synced
from generated meeting insights and can be tracked by status, owner, due date,
and priority. The dashboard includes accountability summaries, prioritized
drilldown, and follow-up views.

**Phases 9F–9J — history, signal review, analytics, and drilldown:** Database
migrations add action-item change history, database-derived accountability
signals, an acknowledgement workflow, review analytics, and review-state
filtering in the paginated drilldown. These SQL changes must be applied and
verified separately for each database.

### Authentication routes

- `/login` — email/password login
- `/signup` — email/password registration with password confirmation
- `/dashboard` — protected authenticated application shell

Supabase email confirmation may be enabled for the project. When enabled,
signup asks the user to confirm their email; the confirmation callback
establishes the session and returns them to the dashboard.

## Future development

Remaining work includes search across meeting content, RAG and pgvector,
additional AI providers and local inference, diarization, exports, deployment,
and production hardening. These items are planned and are not implied to be
implemented by the completed phases above.
