# Meeting Intelligence System

A planned application for organizing meetings and turning their recordings into
searchable transcripts, summaries, decisions, and follow-up work. This
repository is in the **initial project setup (Phase 0)**: it contains a Next.js
frontend foundation and a minimal FastAPI health endpoint only.

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
- **Database:** PostgreSQL, pgvector (planned)
- **Authentication and file storage:** Supabase Auth and Supabase Storage (planned)
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

See [docs/architecture.md](docs/architecture.md) for the planned architecture.
No database, authentication, AI, media processing, or business features are
implemented in Phase 0.

## Repository structure

```text
meeting-intelligence-system/
├── frontend/                  # Next.js + TypeScript + Tailwind foundation
├── backend/                   # FastAPI app and Python dependencies
│   └── app/
├── database/                  # Planned PostgreSQL/pgvector schema and migrations
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

Use `.env.example` as a reference for local configuration. When needed, put
`NEXT_PUBLIC_` values in `frontend/.env.local` and server-only values such as
`SUPABASE_SERVICE_ROLE_KEY`, database credentials, and AI provider keys in the
backend environment. Leave values blank until their integrations are
implemented. Never commit `.env` files or credentials.

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

## Current project status

**Phase 0 — foundation:** Complete. The Next.js + TypeScript + Tailwind
frontend, minimal FastAPI health endpoint, initial backend dependencies, and
project documentation are in place. Authentication, database schema, AI
integrations, uploads, and all user-facing product features remain planned.

## Future development phases

1. Establish database schema and migrations, then authentication and storage.
2. Add project/meeting workflows and secure media handling.
3. Add transcription, diarization, summaries, and structured meeting insights.
4. Add provider-backed RAG, meeting search, and tracking workflows.
5. Add analytics, exports, deployment, and production hardening.

These phases are a roadmap, not a claim that those capabilities already exist.
