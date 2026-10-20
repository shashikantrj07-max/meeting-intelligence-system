"use client";

import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

import { getSupabaseConfig } from "./config";

let supabase: SupabaseClient | undefined;

export function createClient() {
  if (!supabase) {
    const { url, anonKey } = getSupabaseConfig();
    supabase = createBrowserClient(url, anonKey);
  }

  return supabase;
}
