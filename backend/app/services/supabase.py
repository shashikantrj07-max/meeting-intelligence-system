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