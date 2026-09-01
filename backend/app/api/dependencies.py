import hashlib
import hmac
import json
from typing import Optional
from fastapi import Cookie, Depends, HTTPException, Request, Response, status
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.models.db import User
from backend.app.observability.logging import get_logger
from backend.app.persistence.db import get_db
from backend.app.persistence.repositories import UserRepository

logger = get_logger("rebutio.auth")


def create_test_auth_token(user_id: str) -> str:
    secret = settings.INSFORGE_JWT_SECRET or settings.REBUTIO_SESSION_SECRET or "test-secret"
    return jwt.encode({"sub": user_id, "aud": "insforge"}, secret, algorithm="HS256")


def sign_user_id(user_id: str) -> str:
    return create_test_auth_token(user_id)



def extract_bearer_token(request: Request, cookie_token: Optional[str] = None) -> Optional[str]:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.strip().lower().startswith("bearer "):
        return auth_header.strip()[7:].strip()

    insforge_header = request.headers.get("x-insforge-token") or request.headers.get("X-InsForge-Token")
    if insforge_header:
        return insforge_header.strip()

    if cookie_token:
        return cookie_token.strip()

    return None


def verify_insforge_jwt(token: str) -> Optional[str]:
    """
    Verifies InsForge JWT token server-side and extracts the verified subject/user_id.
    Never trusts client user IDs.
    """
    secrets_to_try = []
    if settings.INSFORGE_JWT_SECRET:
        secrets_to_try.append((settings.INSFORGE_JWT_SECRET, ["HS256"]))
    if settings.INSFORGE_JWT_PUBLIC_KEY:
        secrets_to_try.append((settings.INSFORGE_JWT_PUBLIC_KEY, ["RS256"]))
    if settings.REBUTIO_SESSION_SECRET and settings.ENVIRONMENT != "production":
        secrets_to_try.append((settings.REBUTIO_SESSION_SECRET, ["HS256"]))

    # Try cryptographic verification with configured keys
    for secret_key, algos in secrets_to_try:
        try:
            payload = jwt.decode(
                token,
                secret_key,
                algorithms=algos,
                options={"verify_aud": False, "verify_signature": True},
            )
            user_id = payload.get("sub") or payload.get("id") or payload.get("user_id")
            if user_id and isinstance(user_id, str):
                return user_id
        except Exception:
            continue

    # Unverified decode fallback ONLY if explicit development bypass is enabled
    if settings.ALLOW_DEV_AUTH_BYPASS and settings.ENVIRONMENT in ("test", "development"):
        try:
            unverified_payload = jwt.decode(
                token,
                options={"verify_signature": False, "verify_aud": False},
            )
            user_id = unverified_payload.get("sub") or unverified_payload.get("id")
            if user_id and isinstance(user_id, str):
                return user_id
        except Exception:
            pass

    return None


def verify_test_or_legacy_token(token: str, request: Request) -> Optional[str]:
    """
    Test and development authorization verification.
    Strictly active only when ALLOW_DEV_AUTH_BYPASS=True in non-production.
    Never active in production.
    """
    if not (settings.ALLOW_DEV_AUTH_BYPASS and settings.ENVIRONMENT in ("test", "development")):
        return None

    # Allow simple test user IDs when in test/dev mode with explicit bypass
    if token.startswith("test-") or token.startswith("user-") or token.startswith("mock-"):
        return token

    test_header = request.headers.get("X-Test-User-ID")
    if test_header:
        return test_header.strip()

    return None


async def get_current_user(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    insforge_access_token: Optional[str] = Cookie(None),
    rebutio_session: Optional[str] = Cookie(None),
) -> User:
    """
    Verifies authenticated user identity server-side using InsForge Bearer token.
    Derives user ID strictly from the verified auth token.
    Never trusts client-provided user IDs.
    Fails closed when no verified token is provided.
    """
    token = extract_bearer_token(request, cookie_token=insforge_access_token or (rebutio_session if settings.ALLOW_DEV_AUTH_BYPASS else None))
    user_id = None

    if token:
        user_id = verify_insforge_jwt(token)
        if not user_id:
            user_id = verify_test_or_legacy_token(token, request)

    if not user_id and settings.ALLOW_DEV_AUTH_BYPASS and settings.ENVIRONMENT in ("test", "development"):
        # Explicit bypass only: default to a stable verified local dev identity
        user_id = request.headers.get("X-Test-User-ID") or "default-user-id"

    if not user_id:
        logger.warning("auth.unauthorized_request", path=request.url.path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication token. Please sign in via InsForge.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_repo = UserRepository(db)
    user = await user_repo.get_or_create_user(user_id)
    return user
