# Frontend

The frontend is a Next.js App Router application using React, TypeScript, and
Tailwind CSS. It provides Supabase email/password authentication and the
authenticated meeting workspace: meeting management, transcript editing,
meeting insights, tracked action items, accountability/history/review, and
review analytics. The dashboard can search meeting titles and indexed
transcript content without loading transcript bodies into the browser.

Browser-side meeting and transcript operations use the signed-in Supabase
session and rely on database row-level security. Action-item, insight, and
transcription operations call the FastAPI backend. Authenticated pages are
checked server-side; this is not a replacement for authorization in the
backend or database.

## Prerequisites

- Node.js compatible with the installed Next.js 16 version and npm.
- A configured Supabase project with the required migrations applied; see
  [`../database/README.md`](../database/README.md).
- The FastAPI backend running for action-item, insight, and transcription
  requests. The frontend server and backend are separate processes.

## Configuration

Create `frontend/.env.local` locally with these variable names:

| Name | Used for |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL used by browser and server Supabase clients. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Public Supabase anon key used with the signed-in session. Never use a service-role key. |
| `NEXT_PUBLIC_API_BASE_URL` | Base URL of the FastAPI backend, for example the local API origin. |

Only the Supabase URL and anon key belong in frontend configuration. The API
base URL is also public configuration. Do not put database credentials,
Gemini keys, service-role keys, or other private values in `NEXT_PUBLIC_`
variables or frontend files. Do not commit `.env.local`.

Configure Supabase Auth's local site URL and redirect allowlist for the local
frontend origin and `/auth/callback`. Signup behavior depends on the project's
email-confirmation settings.

## Install and run

From this directory:

```powershell
npm ci
npm run dev
```

Open `http://localhost:3000`. Start the backend separately; setup instructions
are in [`../backend/README.md`](../backend/README.md).

## Checks

Available package scripts and repository tests:

```powershell
npm run lint
npx tsc --noEmit
node --test tests\dashboard-accountability.test.mjs tests\dashboard-meetings.test.mjs tests\meeting-action-items.test.mjs
```

`npm run build` is also available, but a production build writes generated
Next.js output to `.next`. The Node tests cover dashboard/action-item parsing,
formatting, and state helpers; they do not replace browser end-to-end testing
or validate Supabase, backend, or external-service availability.

## Limitations

File uploads go directly from the browser to the private Supabase Storage
bucket and are limited in the UI to 500 MiB. Transcription is performed locally
by the backend's Whisper/FFmpeg workflow, not by the frontend. The frontend
depends on the backend, Supabase Auth, database schema, Storage policies, and
the configured Gemini service for the corresponding features to work; this
README does not claim those external services are live or verified.
