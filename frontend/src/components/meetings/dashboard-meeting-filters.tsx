"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import type { FormEvent } from "react";

import type { DashboardFilters } from "@/lib/dashboard-meetings";

type DashboardMeetingFiltersProps = {
  filters: DashboardFilters;
  hasActiveFilters: boolean;
};

export function DashboardMeetingFilters({
  filters,
  hasActiveFilters,
}: DashboardMeetingFiltersProps) {
  const router = useRouter();
  const formKey = `${filters.search}:${filters.status}`;

  function navigate(form: HTMLFormElement) {
    const values = new FormData(form);
    const query = new URLSearchParams();
    const search = values.get("q");
    const status = values.get("status");

    if (typeof search === "string" && search.trim()) {
      query.set("q", search.trim().slice(0, 200));
    }
    if (typeof status === "string" && status !== "all") {
      query.set("status", status);
    }

    const queryString = query.toString();
    router.push(queryString ? `/dashboard?${queryString}` : "/dashboard");
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
          Search meeting titles
        </label>
        <input
          autoComplete="off"
          className="mt-2 block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm text-zinc-950 shadow-sm outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
          id="meeting-search"
          maxLength={200}
          name="q"
          placeholder="Search meetings"
          type="search"
          defaultValue={filters.search}
        />
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
