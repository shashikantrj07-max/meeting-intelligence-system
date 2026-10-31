from supabase import Client, create_client

from app.config import settings


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
    service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY
    if not service_role_key or not service_role_key.strip():
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is required to run the processing worker."
        )

    return create_client(settings.SUPABASE_URL, service_role_key)