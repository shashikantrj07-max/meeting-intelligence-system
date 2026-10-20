"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { createClient } from "@/lib/supabase/client";
import { AuthProvider, useAuth } from "./auth-context";

type AuthenticatedShellProps = {
  email: string;
  children: React.ReactNode;
};

export function AuthenticatedShell({
  email,
  children,
}: AuthenticatedShellProps) {
  return (
    <AuthProvider initialEmail={email}>
      <AuthenticatedContent>{children}</AuthenticatedContent>
    </AuthProvider>
  );
}

function AuthenticatedContent({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { email } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  async function handleLogout() {
    setIsLoading(true);
    setErrorMessage("");

    try {
      const { error } = await createClient().auth.signOut();
      if (error) {
        setErrorMessage("Unable to log out. Please try again.");
        return;
      }

      router.replace("/login");
      router.refresh();
    } catch {
      setErrorMessage("Something went wrong. Please try again.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-zinc-50">
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <Link href="/dashboard" className="font-semibold text-zinc-950">
            Meeting Intelligence System
          </Link>
          <nav
            aria-label="Main navigation"
            className="flex items-center gap-5 text-sm"
          >
            <Link
              href="/dashboard"
              className="font-medium text-blue-700 hover:text-blue-800"
            >
              Dashboard
            </Link>
            <span className="max-w-48 break-all text-zinc-600">{email}</span>
            <button
              type="button"
              onClick={handleLogout}
              disabled={isLoading}
              className="rounded-lg border border-zinc-300 px-3 py-2 font-medium text-zinc-800 transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoading ? "Logging out..." : "Log out"}
            </button>
          </nav>
        </div>
        {errorMessage && (
          <p
            role="alert"
            className="mx-auto max-w-6xl px-6 pb-3 text-sm text-red-800"
          >
            {errorMessage}
          </p>
        )}
      </header>
      {children}
    </div>
  );
}
