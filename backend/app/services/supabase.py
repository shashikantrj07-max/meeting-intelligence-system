from supabase import Client, create_client

from app.config import settings


class WorkerSupabaseClientInitializationError(RuntimeError):
    """A safe, categorized failure while creating the worker Supabase client."""

    def __init__(self, category: str, *, cause_type: str | None = None) -> None:
        self.category = category
        self.cause_type = cause_type
        super().__init__(f"Worker Supabase initialization failed: {category}")


def create_request_supabase_client(access_token: str) -> Client:
    """Create a Supabase client scoped to one caller's access token."""
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)

    client.postgrest.auth(access_token)
    client.storage._client.headers.update(
        {
            "Authorization": f"Bearer {access_token}",
        }
    )

    return client


def create_worker_supabase_client() -> Client:
    """Create the server-only Supabase client used by the durable worker."""
    supabase_url = settings.SUPABASE_URL
    if not isinstance(supabase_url, str) or not supabase_url.strip():
        raise WorkerSupabaseClientInitializationError("missing_supabase_url")

    service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY
    if not service_role_key or not service_role_key.strip():
        raise WorkerSupabaseClientInitializationError(
            "missing_service_role_configuration"
        )

    try:
        return create_client(supabase_url, service_role_key)
    except Exception as exc:
        raise WorkerSupabaseClientInitializationError(
            "supabase_client_construction_failure",
            cause_type=type(exc).__name__,
        ) from exc
