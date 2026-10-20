import { Suspense } from "react";
import { redirect } from "next/navigation";

import { AuthenticatedShell } from "@/components/auth/authenticated-shell";
import { createClient } from "@/lib/supabase/server";

export default async function AuthenticatedLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <Suspense
      fallback={
        <div className="p-6 text-sm text-zinc-600">
          Loading your workspace...
        </div>
      }
    >
      <AuthenticatedContent>{children}</AuthenticatedContent>
    </Suspense>
  );
}

async function AuthenticatedContent({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const supabase = await createClient();
  const {
    data: { user },
    error,
  } = await supabase.auth.getUser();

  if (error) {
    throw error;
  }

  if (!user) {
    redirect("/login");
  }

  return (
    <AuthenticatedShell email={user.email ?? ""}>
      {children}
    </AuthenticatedShell>
  );
}
