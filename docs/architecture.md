# Planned Architecture

This document describes the intended system. The integrations and product
features below are planned and are not yet implemented.

## Components

- **Frontend (`frontend/`)**: Next.js, React, TypeScript, Tailwind CSS, and
  shadcn/ui for the user interface. It communicates with the backend over HTTP
  and must not contain private API keys or privileged database credentials.
- **Backend (`backend/`)**: Python and FastAPI for API endpoints, validation,
  business logic, privileged database operations, file processing, AI
  orchestration, transcription, RAG, and export generation.
- **Database (`database/`)**: PostgreSQL with pgvector for relational data and
  vector search. Schema and migrations are planned for a later phase.
- **Authentication and storage**: Supabase Auth and Supabase Storage are planned
  integrations. The frontend may use only public client configuration; service
  role credentials remain server-side.

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
