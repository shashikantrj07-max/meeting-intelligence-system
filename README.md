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
- **Meeting-content search:** search meeting titles and indexed transcript
  content from the dashboard, with bounded results and short context snippets.
- **Database ownership controls:** migrations define row-level security for
  meeting-owned data and restricted access to action-item history and review
  state. The API routes that handle action-item, transcription, and insight
  requests verify Supabase bearer tokens; this does not imply that every API
  route in the repository has the same authentication behavior.

Migrations and tests are source files, not proof that a particular database has
been migrated. Apply them to a development database and run the matching
verification scripts as described in [database/README.md](database/README.md).

## Planned functionality

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

Requirements: Node.js compatible with the installed Next.js version, npm,
Python 3.12 (or a version compatible with the installed Whisper/PyTorch
dependencies), FFmpeg on the backend host for media transcription, a Supabase
project, and a Gemini API key for meeting-insight generation. The frontend and
backend are installed and started independently. External services and local
media-processing requirements must be configured and validated for each
development environment.

### Environment variables

Configure the frontend and backend separately. Create `frontend/.env.local`
with these names:

| Variable | Used by |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Frontend Supabase client. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Frontend Supabase client; public anon key only. |
| `NEXT_PUBLIC_API_BASE_URL` | Frontend requests to the FastAPI backend. |

Configure the backend through `backend/.env` or its process environment:

| Variable | Required | Used by |
|---|---|---|
| `SUPABASE_URL` | Yes | Backend Supabase client. |
| `SUPABASE_ANON_KEY` | Yes | Backend Supabase client, used with the caller's bearer token. |
| `GEMINI_API_KEY` | Yes | Gemini meeting-insight generation. |
| `GEMINI_MODEL` | No | Gemini model selection; defaults to `gemini-3.8-flash`. |
| `SUPABASE_SERVICE_ROLE_KEY` | Worker only | Server-side durable job claiming and private media access. |

The Supabase anon key and project URL are public client configuration. Never
put a service-role key, database credential, Gemini key, or other private
secret in frontend code or any `NEXT_PUBLIC_` variable. Do not commit any
`.env` file. Backend configuration details are in
[backend/README.md](backend/README.md).

```powershell
@'
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_API_BASE_URL=
'@ | Set-Content -Encoding ascii frontend\.env.local
```

Fill these settings locally from the appropriate project configuration. In
Supabase Auth settings, configure the local site URL and allow the local
frontend's `/auth/callback` URL as a redirect. Do not copy `.env.example`
wholesale into either application environment.

### Frontend setup

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://localhost:3000`. The FastAPI backend must be started separately
for API-backed features. See [frontend/README.md](frontend/README.md) for
frontend-specific commands and tests.

### Backend setup

From the repository root, create and activate a virtual environment and install
the backend dependencies:

```powershell
py -3.12 -m venv backend\.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

Set the backend variables listed above in `backend/.env` or the process
environment, then run the API:

```powershell
cd backend
python -m uvicorn app.main:app --reload
```

The health check is available at `http://127.0.0.1:8000/health` and returns
`{"status":"ok"}`. See [backend/README.md](backend/README.md) for details.
Insight generation and transcription are durably enqueued in Supabase; start a
separate supervised worker from the `backend` directory with
`python -m app.worker`. The worker requires the server-only
`SUPABASE_SERVICE_ROLE_KEY`. Whisper transcription runs on the worker host,
invokes FFmpeg, and may download a model on first use; CPU processing can be
slow.

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

**Phase 10 — indexed meeting-content search:** Authenticated users can search
meeting titles and transcript content through an indexed, owner-scoped database
RPC. Its migration must be applied separately.

**Phase 11 — durable background processing:** Transcription and insight
requests are persisted as retryable jobs with atomic claims, expiring leases,
and fenced result persistence. Migrations
`20261030000100_phase11_durable_processing_jobs.sql` and
`20261031000100_phase11_claim_job_meeting_id_ambiguity.sql` implement the
workflow and correct the claim RPC's ambiguous `meeting_id` conflict target.
In the local demo, the worker claimed and processed a job, and generated
insights and action items appeared on the dashboard and remained visible after
refresh, according to the reported live verification. The worker runs as a
separate process and must be supervised. This local demo result does not imply
production readiness or independently verify crash-recovery behavior.

### Authentication routes

- `/login` — email/password login
- `/signup` — email/password registration with password confirmation
- `/dashboard` — protected authenticated application shell

Supabase email confirmation may be enabled for the project. When enabled,
signup asks the user to confirm their email; the confirmation callback
establishes the session and returns them to the dashboard.

## Future development

Remaining work includes RAG and pgvector, additional AI providers and local
inference, diarization, exports, deployment, and production hardening. These
items are planned and are not implied to be implemented by the completed
phases above.
