# Frontend

The frontend is a Next.js App Router application written in TypeScript and
styled with Tailwind CSS. Its current page is a setup placeholder; product
features are planned for later phases.

## Local setup

From this directory, install dependencies and start the development server:

```powershell
npm install
npm run dev
```

Open `http://localhost:3000`. The frontend can run independently of the backend.
Available checks are:

```powershell
npm run lint
npx tsc --noEmit
npm run build
```

Use the repository root `.env.example` as a reference. Put only
`NEXT_PUBLIC_` configuration in `.env.local`; keep private API keys and
privileged credentials in the backend environment, never in browser code.
