from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user
from backend.app.models.db import User
from backend.app.observability.logging import get_logger
from backend.app.persistence.db import get_db
from backend.app.services.media.storage import media_storage

logger = get_logger("rebutio.api.media")
router = APIRouter(prefix="/api/media", tags=["media"])


@router.get("/{asset_id}/audio")
async def get_media_asset_audio(
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Streams raw audio for an authorized MediaAsset owned by the user.
    """
    result = await media_storage.get_media_bytes(db=db, user_id=user.id, asset_id=asset_id)
    if not result:
        raise HTTPException(status_code=404, detail="Media asset not found or unauthorized")

    audio_bytes, mime_type = result
    return Response(
        content=audio_bytes,
        media_type=mime_type,
        headers={
            "Content-Length": str(len(audio_bytes)),
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/clips/{clip_id}/audio")
async def get_derived_clip_audio(
    clip_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Streams cropped audio for an authorized DerivedAudioClip owned by the user.
    """
    result = await media_storage.get_clip_bytes(db=db, user_id=user.id, clip_id=clip_id)
    if not result:
        raise HTTPException(status_code=404, detail="Derived audio clip not found or unauthorized")

    audio_bytes, mime_type = result
    return Response(
        content=audio_bytes,
        media_type=mime_type,
        headers={
            "Content-Length": str(len(audio_bytes)),
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, max-age=3600",
        },
    )
