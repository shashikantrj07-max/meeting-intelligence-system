# Meeting Intelligence System

A planned application for organizing meetings and turning their recordings into
searchable transcripts, summaries, decisions, and follow-up work. This
repository is in **Phase 4**: it includes Supabase Auth, a protected meeting
workspace, and a meeting transcript table whose row-level security inherits
ownership from its parent meeting.

## Planned features

All features in this section are planned and are not implemented yet:

- Project and meeting management, including audio/video upload
- Transcription and speaker identification
- Summaries, decisions, action items, questions, and risks/blockers
- Chat with meetings using RAG and search across meetings
- Decision/action tracking, analytics, and report exports
- Interchangeable AI providers and local inference

## Technology stack

- **Frontend:** Next.js, React, TypeScript, Tailwind CSS, shadcn/ui (planned)
- **Backend:** Python, FastAPI
- **Database:** PostgreSQL (meeting and transcript schema with RLS);
  pgvector (planned)
- **Authentication and file storage:** Supabase Auth (implemented in Phase 1);
  Supabase Storage (planned)
- **AI:** Gemini primary, Groq secondary, Ollama local alternative (planned)
- **Speech and retrieval:** Whisper, pyannote.audio, LangChain (planned)
- **Charts and deployment:** Recharts, Vercel, Render/Railway, Supabase (planned)

## High-level architecture

The Next.js frontend and FastAPI backend are separate applications. The frontend
will call the backend over HTTP and will not hold private API keys or
server-privileged credentials. The backend will own business logic, privileged
database access, file processing, AI orchestration, transcription, RAG, and
exports. AI providers will be accessed through interchangeable backend
interfaces so application logic is not tied to Gemini.

See [docs/architecture.md](docs/architecture.md) for the architecture and
authentication flow, and [database/README.md](database/README.md) for
migrations and verification. Storage, AI, and media processing are planned
for later phases.

## Repository structure

```text
meeting-intelligence-system/
├── frontend/                  # Next.js + TypeScript + Tailwind foundation
├── backend/                   # FastAPI app and Python dependencies
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

Phase 2 and Phase 4 add PostgreSQL migrations and SQL verification scripts.
They are not automatically applied by starting the frontend or backend. To
apply and verify them against a development database, follow
[database/README.md](database/README.md). The project does not currently
include pgvector, media upload, or AI processing.

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
implemented. Apply the Phase 4 migration to the configured Supabase project
before using the transcript UI; live transcript CRUD and isolation checks
remain pending. No AI summarization, transcription, or media processing is
included.

### Authentication routes

- `/login` — email/password login
- `/signup` — email/password registration with password confirmation
- `/dashboard` — protected authenticated application shell

Supabase email confirmation may be enabled for the project. When enabled,
signup asks the user to confirm their email; the confirmation callback
establishes the session and returns them to the dashboard.

## Future development phases

1. Add secure media upload and storage policies.
2. Add transcription and diarization workflows.
3. Add summaries and structured meeting insights.
4. Add provider-backed RAG, meeting search, and tracking workflows.
5. Add analytics, exports, deployment, and production hardening.

These phases are a roadmap, not a claim that those capabilities already exist.
