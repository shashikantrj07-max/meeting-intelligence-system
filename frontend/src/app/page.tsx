export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col justify-center gap-6 px-6 py-20 sm:px-10">
      <p className="text-sm font-semibold tracking-wide text-blue-700">
        PHASE 0 · PROJECT FOUNDATION
      </p>
      <h1 className="text-4xl font-semibold tracking-tight text-zinc-950 sm:text-5xl">
        Meeting Intelligence System
      </h1>
      <p className="max-w-2xl text-lg leading-8 text-zinc-600">
        The frontend foundation is ready for development. Meeting management,
        transcription, AI, and other product capabilities are planned for
        future phases.
      </p>
      <section
        aria-labelledby="current-scope"
        className="mt-4 rounded-xl border border-zinc-200 bg-white p-6"
      >
        <h2
          id="current-scope"
          className="text-base font-semibold text-zinc-900"
        >
          Current scope
        </h2>
        <p className="mt-2 text-sm leading-6 text-zinc-600">
          This Next.js application is separate from the Python FastAPI backend.
          No authentication, database, or meeting features are implemented yet.
        </p>
      </section>
    </main>
  );
}
