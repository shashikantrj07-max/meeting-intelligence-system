"use client";

import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import type { FormEvent } from "react";

import type { DashboardFilters } from "@/lib/dashboard-meetings";
import { buildDashboardFilterHref } from "@/lib/dashboard-accountability";

type DashboardMeetingFiltersProps = {
  filters: DashboardFilters;
  hasActiveFilters: boolean;
};

export function DashboardMeetingFilters({
  filters,
  hasActiveFilters,
}: DashboardMeetingFiltersProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const formKey = `${filters.search}:${filters.status}`;

  function navigate(form: HTMLFormElement) {
    const values = new FormData(form);
    const search = values.get("q");
    const status = values.get("status");
    router.push(
      buildDashboardFilterHref(
        searchParams.toString(),
        typeof search === "string" ? search : "",
        typeof status === "string" ? status : "all",
      ),
    );
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    navigate(event.currentTarget);
  }

  return (
    <form
      action="/dashboard"
      className="mt-8 grid gap-4 rounded-xl border border-zinc-200 bg-white p-5 sm:grid-cols-[minmax(0,1fr)_12rem_auto]"
      key={formKey}
      method="get"
      onSubmit={handleSubmit}
    >
      <div>
        <label
          className="block text-sm font-medium text-zinc-800"
          htmlFor="meeting-search"
        >
          Search meetings
        </label>
        <input
          autoComplete="off"
          className="mt-2 block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm text-zinc-950 shadow-sm outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
          id="meeting-search"
          maxLength={200}
          minLength={3}
          name="q"
          placeholder="Search titles or transcripts"
          type="search"
          defaultValue={filters.search}
          aria-describedby="meeting-search-help"
        />
        <p className="mt-1 text-xs text-zinc-600" id="meeting-search-help">
          Search titles and transcript text with at least 3 characters. Leave
          blank to view all meetings.
        </p>
      </div>
      <div>
        <label
          className="block text-sm font-medium text-zinc-800"
          htmlFor="meeting-status-filter"
        >
          Status
        </label>
        <select
          className="mt-2 block w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 shadow-sm outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
          id="meeting-status-filter"
          name="status"
          defaultValue={filters.status}
          onChange={(event) => {
            const form = event.currentTarget.form;
            if (form) {
              navigate(form);
            }
          }}
        >
          <option value="all">All</option>
          <option value="processing">Processing</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
        </select>
      </div>
      <div className="flex items-end gap-3">
        <button
          className="rounded-md bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800"
          type="submit"
        >
          Search
        </button>
        {hasActiveFilters ? (
          <Link
            className="rounded-md px-3 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100"
            href="/dashboard"
          >
            Clear
          </Link>
        ) : null}
      </div>
    </form>
  );
}
