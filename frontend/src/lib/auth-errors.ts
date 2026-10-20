import type { AuthError } from "@supabase/supabase-js";

export type AuthMode = "login" | "signup";

export function getAuthErrorMessage(error: AuthError, mode: AuthMode) {
  if (mode === "login") {
    if (error.code === "email_not_confirmed") {
      return "Please confirm your email address before logging in.";
    }

    if (
      error.code === "invalid_credentials" ||
      error.code === "user_not_found" ||
      error.status === 400
    ) {
      return "Invalid email or password.";
    }

    return "Something went wrong. Please try again.";
  }

  if (
    error.code === "invalid_email" ||
    error.code === "email_address_invalid"
  ) {
    return "Enter a valid email address.";
  }

  if (error.code === "weak_password") {
    return "Choose a stronger password and try again.";
  }

  if (
    error.code === "user_already_exists" ||
    error.code === "email_exists"
  ) {
    return "An account with this email already exists. Try logging in.";
  }

  return "Unable to create your account. Please check your details and try again.";
}
