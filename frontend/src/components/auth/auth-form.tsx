"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, type FormEvent, useState } from "react";

import { getAuthErrorMessage, type AuthMode } from "@/lib/auth-errors";
import { createClient } from "@/lib/supabase/client";

type AuthFormProps = {
  mode: AuthMode;
};

export function AuthForm({ mode }: AuthFormProps) {
  const router = useRouter();
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const isSignup = mode === "signup";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage("");
    setSuccessMessage("");

    const formData = new FormData(event.currentTarget);
    const email = String(formData.get("email") ?? "").trim();
    const password = String(formData.get("password") ?? "");
    const confirmPassword = String(formData.get("confirmPassword") ?? "");

    if (!email || !password) {
      setErrorMessage("Enter your email and password.");
      return;
    }

    if (isSignup && password !== confirmPassword) {
      setErrorMessage("Passwords do not match.");
      return;
    }

    setIsLoading(true);

    try {
      const supabase = createClient();

      if (isSignup) {
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: {
            emailRedirectTo: `${window.location.origin}/auth/callback`,
          },
        });

        if (error) {
          setErrorMessage(getAuthErrorMessage(error, mode));
          return;
        }

        if (data.session) {
          router.replace("/dashboard");
          router.refresh();
          return;
        }

        setSuccessMessage(
          "Account created. Check your email to confirm your account.",
        );
        return;
      }

      const { error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (error) {
        setErrorMessage(getAuthErrorMessage(error, mode));
        return;
      }

      router.replace(
        getInternalRedirect(window.location.search, window.location.origin),
      );
      router.refresh();
    } catch {
      setErrorMessage("Something went wrong. Please try again.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-50 px-4 py-12">
      <section className="w-full max-w-md rounded-2xl border border-zinc-200 bg-white p-8 shadow-sm">
        <Link
          href="/"
          className="text-sm font-semibold tracking-wide text-blue-700"
        >
          MEETING INTELLIGENCE SYSTEM
        </Link>
        <h1 className="mt-8 text-2xl font-semibold tracking-tight text-zinc-950">
          {isSignup ? "Create your account" : "Welcome back"}
        </h1>
        <p className="mt-2 text-sm text-zinc-600">
          {isSignup
            ? "Sign up to access your meeting workspace."
            : "Log in to continue to your workspace."}
        </p>

        <form className="mt-8 space-y-5" onSubmit={handleSubmit} noValidate>
          <div>
            <label
              htmlFor="email"
              className="mb-1.5 block text-sm font-medium text-zinc-800"
            >
              Email
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              className="w-full rounded-lg border border-zinc-300 px-3 py-2.5 text-sm outline-none transition focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
            />
          </div>
          <div>
            <label
              htmlFor="password"
              className="mb-1.5 block text-sm font-medium text-zinc-800"
            >
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete={isSignup ? "new-password" : "current-password"}
              required
              className="w-full rounded-lg border border-zinc-300 px-3 py-2.5 text-sm outline-none transition focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
            />
          </div>
          {isSignup && (
            <div>
              <label
                htmlFor="confirmPassword"
                className="mb-1.5 block text-sm font-medium text-zinc-800"
              >
                Confirm password
              </label>
              <input
                id="confirmPassword"
                name="confirmPassword"
                type="password"
                autoComplete="new-password"
                required
                className="w-full rounded-lg border border-zinc-300 px-3 py-2.5 text-sm outline-none transition focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
              />
            </div>
          )}

          {errorMessage && (
            <p
              role="alert"
              className="rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-800"
            >
              {errorMessage}
            </p>
          )}
          {!isSignup && (
            <Suspense fallback={null}>
              <ConfirmationError />
            </Suspense>
          )}
          {successMessage && (
            <p
              role="status"
              className="rounded-lg bg-green-50 px-3 py-2.5 text-sm text-green-800"
            >
              {successMessage}
            </p>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full rounded-lg bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isLoading
              ? isSignup
                ? "Creating account..."
                : "Logging in..."
              : isSignup
                ? "Create account"
                : "Login"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-zinc-600">
          {isSignup ? "Already have an account?" : "Don't have an account?"}{" "}
          <Link
            href={isSignup ? "/login" : "/signup"}
            className="font-medium text-blue-700 hover:text-blue-800"
          >
            {isSignup ? "Login" : "Sign up"}
          </Link>
        </p>
      </section>
    </main>
  );
}

function getInternalRedirect(search: string, origin: string) {
  const next = new URLSearchParams(search).get("next");

  if (
    !next ||
    !next.startsWith("/") ||
    next.startsWith("//") ||
    next.includes("\\")
  ) {
    return "/dashboard";
  }

  try {
    const destination = new URL(next, origin);
    if (destination.origin !== origin) {
      return "/dashboard";
    }

    return `${destination.pathname}${destination.search}${destination.hash}`;
  } catch {
    return "/dashboard";
  }
}

function ConfirmationError() {
  const searchParams = useSearchParams();

  if (searchParams.get("error") !== "confirmation") {
    return null;
  }

  return (
    <p
      role="alert"
      className="rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-800"
    >
      We couldn&apos;t confirm your email. Try logging in if your account is
      already confirmed.
    </p>
  );
}
