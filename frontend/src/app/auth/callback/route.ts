import { NextResponse, type NextRequest } from "next/server";

import { createClient } from "@/lib/supabase/server";

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");

  if (!code) {
    return NextResponse.redirect(
      new URL("/login?error=confirmation", request.url),
    );
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    return NextResponse.redirect(
      new URL("/login?error=confirmation", request.url),
    );
  }

  const requestedPath = request.nextUrl.searchParams.get("next") ?? "/dashboard";
  const destination = new URL(requestedPath, request.url);
  const safeDestination =
    destination.origin === request.nextUrl.origin
      ? destination
      : new URL("/dashboard", request.url);

  return NextResponse.redirect(safeDestination);
}
