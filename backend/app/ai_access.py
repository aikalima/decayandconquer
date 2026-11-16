"""Google identity verification for paid AI routes; no development bypass."""
import os
import time
from functools import lru_cache

from fastapi import Header, HTTPException
from google.auth.exceptions import GoogleAuthError, TransportError
from google.auth.transport.requests import Request
from google.oauth2 import id_token


def auth_config() -> dict:
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    return {"client_id": client_id, "configured": bool(client_id)}


@lru_cache(maxsize=128)
def _verify(token: str, client_id: str) -> dict:
    # Only successfully verified tokens are cached. Expiry is checked on every
    # request, including cache hits. Google sub, not email, owns the allowance.
    def transport(*args, **kwargs):
        kwargs["timeout"] = 10
        return Request()(*args, **kwargs)
    return id_token.verify_oauth2_token(token, transport, audience=client_id)


def require_ai_user(authorization: str | None = Header(default=None)) -> dict:
    config = auth_config()
    if not config["configured"]:
        raise HTTPException(503, "AI sign-in is not configured. The public dashboard is still available.")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 8192:
        raise HTTPException(401, "Sign in with Google to use Dacey and Market Context.",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = _verify(token, config["client_id"])
        if (not claims.get("sub") or claims.get("exp", 0) <= time.time()
                or claims.get("email_verified") is not True):
            raise ValueError("Invalid identity")
    except TransportError as exc:
        raise HTTPException(503, "Google sign-in verification is temporarily unavailable.") from exc
    except (ValueError, GoogleAuthError) as exc:
        raise HTTPException(401, "Your sign-in expired or is invalid. Sign in again.",
                            headers={"WWW-Authenticate": "Bearer"}) from exc
    email = claims.get("email", "").lower()
    return {"sub": claims["sub"], "email": email, "expires_at": claims["exp"]}
