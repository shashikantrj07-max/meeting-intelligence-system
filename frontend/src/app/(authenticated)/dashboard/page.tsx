"use client";

import { useAuth } from "@/components/auth/auth-context";

export default function DashboardPage() {
  const { email } = useAuth();

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <p className="text-sm font-semibold tracking-wide text-blue-700">
        DASHBOARD
      </p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-950">
        Welcome, {email}
      </h1>
      <p className="mt-3 text-zinc-600">
        Your meeting intelligence workspace is ready.
      </p>
    </main>
  );
}
