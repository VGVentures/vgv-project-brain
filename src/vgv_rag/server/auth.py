import asyncio
from vgv_rag.storage.client import get_client

ALLOWED_DOMAIN = "@verygood.ventures"


async def validate_jwt(token: str) -> str:
    """Validate a Supabase JWT and return the user's email."""
    client = get_client()
    response = await asyncio.to_thread(lambda: client.auth.get_user(token))

    if response.error or not response.user or not response.user.email:
        raise PermissionError("Unauthorized: invalid token")

    if not response.user.email.endswith(ALLOWED_DOMAIN):
        raise PermissionError("Unauthorized: not a VGV account")

    return response.user.email


def extract_bearer_token(auth_header: str | None) -> str | None:
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    return auth_header[len("Bearer "):]
