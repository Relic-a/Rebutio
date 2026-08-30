import hashlib
import hmac
import uuid
from typing import Optional
from fastapi import Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.models.db import User
from backend.app.persistence.db import get_db
from backend.app.persistence.repositories import UserRepository


def sign_user_id(user_id: str) -> str:
    secret = settings.REBUTIO_SESSION_SECRET.encode("utf-8")
    sig = hmac.new(secret, user_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{user_id}.{sig}"


def verify_signed_user_id(signed_value: str) -> Optional[str]:
    if not signed_value or "." not in signed_value:
        return None
    user_id, sig = signed_value.split(".", 1)
    secret = settings.REBUTIO_SESSION_SECRET.encode("utf-8")
    expected_sig = hmac.new(secret, user_id.encode("utf-8"), hashlib.sha256).hexdigest()
    if hmac.compare_digest(sig, expected_sig):
        return user_id
    return None


async def get_current_user(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    rebutio_session: Optional[str] = Cookie(None),
) -> User:
    """
    Retrieves or establishes the anonymous authenticated user identity via secure signed cookie.
    """
    user_repo = UserRepository(db)
    user_id = None

    if rebutio_session:
        user_id = verify_signed_user_id(rebutio_session)

    if not user_id:
        # Check custom header if provided by frontend
        header_user_id = request.headers.get("X-User-ID")
        if header_user_id:
            user_id = header_user_id

    if not user_id:
        user_id = str(uuid.uuid4())
        signed_cookie = sign_user_id(user_id)
        response.set_cookie(
            key=settings.SESSION_COOKIE_NAME,
            value=signed_cookie,
            max_age=settings.SESSION_COOKIE_MAX_AGE_DAYS * 86400,
            httponly=True,
            samesite="lax",
            secure=settings.COOKIE_SECURE,
        )

    user = await user_repo.get_or_create_user(user_id)
    return user
