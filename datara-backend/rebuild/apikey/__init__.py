"""Open API key management domain (hash-only credentials)."""

from rebuild.apikey.api import build_apikey_router
from rebuild.apikey.migrations import apply_apikey_migrations
from rebuild.apikey.models import ApiKeyRecord
from rebuild.apikey.service import ApiKeyAuthError, ApiKeyPrincipal, ApiKeyVerifier

__all__ = [
    "ApiKeyRecord", "ApiKeyAuthError", "ApiKeyPrincipal", "ApiKeyVerifier",
    "apply_apikey_migrations", "build_apikey_router",
]
