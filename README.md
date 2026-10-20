# Meeting Intelligence System

A planned application for organizing meetings and turning their recordings into
searchable transcripts, summaries, decisions, and follow-up work. This
repository is in **Phase 2**: it includes the Phase 1 Supabase Auth application
shell and an additive PostgreSQL schema migration with ownership-based row
level security. The migration and database verification scripts still need to
be applied and run against a Supabase/PostgreSQL development database.

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
- **Database:** PostgreSQL (initial schema migration added in Phase 2);
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
migrations and verification. Storage, AI, media processing, and meeting
features are planned for later phases.

## Repository structure

```text
meeting-intelligence-system/
├── frontend/                  # Next.js + TypeScript + Tailwind foundation
├── backend/                   # FastAPI app and Python dependencies
│   └── app/
├── database/                  # PostgreSQL migration and verification scripts
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

Phase 2 adds a PostgreSQL migration and SQL verification scripts. They are not
automatically applied by starting the frontend or backend. To apply and verify
them against a development database, follow [database/README.md](database/README.md).
The project does not currently include pgvector, meeting-content tables, or
database-backed application behavior.

## Current project status

**Phase 1 — authentication and application shell:** Implemented. Supabase Auth
provides signup and password login; authenticated users can access the
protected dashboard, see their email, and log out.

**Phase 2 — database foundation:** Migration, owner-scoped RLS policies,
profile trigger/backfill, schema verification SQL, and manual TypeScript
database types have been added. Applying the migration and running database
verification against a real development database remain outstanding. No
meeting workflows, AI, or media processing are implemented.

### Authentication routes

- `/login` — email/password login
- `/signup` — email/password registration with password confirmation
- `/dashboard` — protected authenticated application shell

Supabase email confirmation may be enabled for the project. When enabled,
signup asks the user to confirm their email; the confirmation callback
establishes the session and returns them to the dashboard.

## Future development phases

1. Apply and validate the database foundation; implement storage policies and
   secure media handling.
2. Add project/meeting workflows.
3. Add transcription, diarization, summaries, and structured meeting insights.
4. Add provider-backed RAG, meeting search, and tracking workflows.
5. Add analytics, exports, deployment, and production hardening.

These phases are a roadmap, not a claim that those capabilities already exist.
