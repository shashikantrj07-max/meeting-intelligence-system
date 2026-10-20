"use client";

import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";

const AuthContext = createContext<{ email: string } | null>(null);

export function AuthProvider({
  initialEmail,
  children,
}: {
  initialEmail: string;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [email, setEmail] = useState(initialEmail);

  useEffect(() => {
    const {
      data: { subscription },
    } = createClient().auth.onAuthStateChange((event, session) => {
      setEmail(session?.user.email ?? "");
      if (event === "SIGNED_OUT") {
        router.replace("/login");
        router.refresh();
      }
    });

    return () => subscription.unsubscribe();
  }, [router]);

  return (
    <AuthContext.Provider value={{ email }}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider.");
  }
  return context;
}
