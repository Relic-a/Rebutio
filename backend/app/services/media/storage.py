import abc
import asyncio
import datetime
import os
import shutil
import tempfile
import uuid
from typing import Any, Dict, List, Optional, Tuple
import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.config import settings
from backend.app.models.db import DerivedAudioClip, MediaAsset, utcnow
from backend.app.observability.logging import get_logger
from backend.app.services.privacy.encryption import encryptor

logger = get_logger("rebutio.media_storage")


class MediaStorageService(abc.ABC):
    @abc.abstractmethod
    async def save_media_asset(
        self,
        db: AsyncSession,
        user_id: str,
        audio_bytes: bytes,
        mime_type: str = "audio/webm",
        source_type: str = "debate_turn",
        session_id: Optional[str] = None,
        turn_number: Optional[int] = None,
        transcript: Optional[str] = None,
        phonemes: Optional[List[dict]] = None,
        speech_metrics: Optional[dict] = None,
        duration_ms: int = 0,
        expires_in_hours: Optional[int] = None,
    ) -> MediaAsset:
        pass

    @abc.abstractmethod
    async def get_media_bytes(
        self,
        db: AsyncSession,
        user_id: str,
        asset_id: str,
    ) -> Optional[Tuple[bytes, str]]:
        pass

    @abc.abstractmethod
    async def create_derived_clip(
        self,
        db: AsyncSession,
        user_id: str,
        source_asset_id: str,
        start_ms: int,
        end_ms: int,
        purpose: str = "evidence",
        label: str = "Debate Evidence",
        transcript_excerpt: Optional[str] = None,
        coach_note: Optional[str] = None,
    ) -> DerivedAudioClip:
        pass

    @abc.abstractmethod
    async def get_clip_bytes(
        self,
        db: AsyncSession,
        user_id: str,
        clip_id: str,
    ) -> Optional[Tuple[bytes, str]]:
        pass

    @abc.abstractmethod
    async def cleanup_expired_assets(self, db: AsyncSession) -> int:
        pass


class InsForgeMediaStorageService(MediaStorageService):
    """
    InsForge BaaS Private Media Storage Service.
    Persists debate speech audio and coaching evidence clips to the private
    InsForge 'rebutio-media' storage bucket.
    """

    def __init__(self, bucket_name: Optional[str] = None):
        self.bucket_name = bucket_name or settings.STORAGE_BUCKET_NAME
        self.insforge_url = settings.INSFORGE_URL.rstrip("/")
        self.api_key = settings.INSFORGE_API_KEY or settings.INSFORGE_ANON_KEY or ""
        # Local fallback cache for seamless local testing / offline dev
        self._local_fallback_cache: Dict[str, bytes] = {}

    def _get_auth_headers(self, mime_type: Optional[str] = None) -> Dict[str, str]:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if mime_type:
            headers["Content-Type"] = mime_type
        return headers

    def _get_ext_from_mime(self, mime_type: str) -> str:
        mime = mime_type.lower()
        if "webm" in mime:
            return "webm"
        if "wav" in mime:
            return "wav"
        if "mp3" in mime or "mpeg" in mime:
            return "mp3"
        if "ogg" in mime:
            return "ogg"
        if "m4a" in mime or "mp4" in mime or "aac" in mime:
            return "m4a"
        return "webm"

    @staticmethod
    def _is_expired(expires_at: Optional[datetime.datetime]) -> bool:
        if not expires_at:
            return False
        now = utcnow()
        if expires_at.tzinfo is None and now.tzinfo is not None:
            now = now.replace(tzinfo=None)
        elif expires_at.tzinfo is not None and now.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=None)
        return expires_at < now

    async def _upload_to_insforge(self, object_path: str, data: bytes, mime_type: str) -> bool:
        url = f"{self.insforge_url}/api/storage/buckets/{self.bucket_name}/objects/{object_path}"
        headers = self._get_auth_headers(mime_type)
        upload_error = None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, content=data, headers=headers)
                if res.status_code in (200, 201, 204):
                    logger.info("insforge.storage.uploaded", bucket=self.bucket_name, path=object_path, size=len(data))
                    return True
                # If POST not allowed or object exists, try PUT
                if res.status_code in (405, 409):
                    res_put = await client.put(url, content=data, headers=headers)
                    if res_put.status_code in (200, 201, 204):
                        return True
                upload_error = f"HTTP {res.status_code}: {res.text[:200]}"
                logger.warning("insforge.storage.upload_response", status=res.status_code, path=object_path)
        except Exception as e:
            upload_error = str(e)
            logger.warning("insforge.storage.upload_network_error", path=object_path, error=upload_error)

        # In production, NEVER silently fall back to in-memory cache and never pretend file was uploaded!
        if settings.ENVIRONMENT == "production":
            logger.error("insforge.storage.upload_failed_in_production", path=object_path, error=upload_error)
            raise RuntimeError(f"Failed to upload media to InsForge storage in production: {upload_error}")

        # Local/test mode fallback only
        self._local_fallback_cache[object_path] = data
        return True

    async def _download_from_insforge(self, object_path: str) -> Optional[bytes]:
        if settings.ENVIRONMENT != "production" and object_path in self._local_fallback_cache:
            return self._local_fallback_cache[object_path]

        url = f"{self.insforge_url}/api/storage/buckets/{self.bucket_name}/objects/{object_path}"
        headers = self._get_auth_headers()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    return res.content
                logger.warning("insforge.storage.download_response", status=res.status_code, path=object_path)
        except Exception as e:
            logger.warning("insforge.storage.download_network_error", path=object_path, error=str(e))

        return None

    async def _delete_from_insforge(self, object_path: str) -> bool:
        self._local_fallback_cache.pop(object_path, None)
        url = f"{self.insforge_url}/api/storage/buckets/{self.bucket_name}/objects/{object_path}"
        headers = self._get_auth_headers()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.delete(url, headers=headers)
                return res.status_code in (200, 204, 404)
        except Exception as e:
            logger.warning("insforge.storage.delete_network_error", path=object_path, error=str(e))
            return False

    async def save_media_asset(
        self,
        db: AsyncSession,
        user_id: str,
        audio_bytes: bytes,
        mime_type: str = "audio/webm",
        source_type: str = "debate_turn",
        session_id: Optional[str] = None,
        turn_number: Optional[int] = None,
        transcript: Optional[str] = None,
        phonemes: Optional[List[dict]] = None,
        speech_metrics: Optional[dict] = None,
        duration_ms: int = 0,
        expires_in_hours: Optional[int] = None,
    ) -> MediaAsset:
        asset_id = f"asset-{uuid.uuid4().hex[:12]}"
        ext = self._get_ext_from_mime(mime_type)
        object_path = f"{user_id}/{asset_id}.{ext}"

        # Upload to InsForge Storage bucket
        await self._upload_to_insforge(object_path, audio_bytes, mime_type)

        if duration_ms <= 0:
            duration_ms = max(500, min(60000, len(audio_bytes) // 32))

        retention_hours = expires_in_hours if expires_in_hours is not None else settings.EVIDENCE_RETENTION_HOURS
        expires_at = utcnow() + datetime.timedelta(hours=retention_hours) if retention_hours > 0 else None

        encrypted_transcript = encryptor.encrypt_str(transcript) if transcript else None
        encrypted_phonemes = encryptor.encrypt_json(phonemes) if phonemes else None

        asset = MediaAsset(
            id=asset_id,
            user_id=user_id,
            session_id=session_id,
            turn_number=turn_number,
            source_type=source_type,
            storage_path=object_path,
            mime_type=mime_type,
            file_size_bytes=len(audio_bytes),
            duration_ms=duration_ms,
            transcript_encrypted=encrypted_transcript,
            phonemes_encrypted=encrypted_phonemes,
            speech_metrics_json=speech_metrics or {},
            expires_at=expires_at,
            created_at=utcnow(),
        )
        db.add(asset)
        await db.commit()
        await db.refresh(asset)

        logger.info(
            "media.asset.saved",
            asset_id=asset_id,
            user_id=user_id,
            source_type=source_type,
            storage="insforge",
            bucket=self.bucket_name,
            path=object_path,
            size_bytes=len(audio_bytes),
            duration_ms=duration_ms,
        )
        return asset

    async def get_media_asset(
        self,
        db: AsyncSession,
        user_id: str,
        asset_id: str,
    ) -> Optional[MediaAsset]:
        stmt = select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.user_id == user_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_media_bytes(
        self,
        db: AsyncSession,
        user_id: str,
        asset_id: str,
    ) -> Optional[Tuple[bytes, str]]:
        asset = await self.get_media_asset(db, user_id, asset_id)
        if not asset:
            logger.warning("media.access.denied_or_missing", asset_id=asset_id, user_id=user_id)
            return None

        if self._is_expired(asset.expires_at):
            logger.info("media.access.expired", asset_id=asset_id)
            return None

        data = await self._download_from_insforge(asset.storage_path)
        if not data:
            logger.error("media.file_missing_in_insforge", asset_id=asset_id, path=asset.storage_path)
            return None

        return data, asset.mime_type

    async def create_derived_clip(
        self,
        db: AsyncSession,
        user_id: str,
        source_asset_id: str,
        start_ms: int,
        end_ms: int,
        purpose: str = "evidence",
        label: str = "Debate Evidence",
        transcript_excerpt: Optional[str] = None,
        coach_note: Optional[str] = None,
    ) -> DerivedAudioClip:
        source_asset = await self.get_media_asset(db, user_id, source_asset_id)
        if not source_asset:
            raise ValueError(f"Source media asset {source_asset_id} not found or unauthorized for user {user_id}")

        source_bytes = await self._download_from_insforge(source_asset.storage_path)
        if not source_bytes:
            raise ValueError(f"Source audio file is not available in storage")

        total_duration = max(1000, source_asset.duration_ms)
        start_ms = max(0, min(start_ms, total_duration - 100))
        end_ms = max(start_ms + 200, min(end_ms, total_duration))
        if end_ms - start_ms > 30000:
            end_ms = start_ms + 30000

        clip_duration_ms = end_ms - start_ms
        clip_id = f"clip-{uuid.uuid4().hex[:12]}"
        clip_object_path = f"{user_id}/clips/{clip_id}.mp3"

        start_sec = start_ms / 1000.0
        dur_sec = clip_duration_ms / 1000.0

        # Perform FFmpeg crop via temp files
        with tempfile.TemporaryDirectory() as tmpdir:
            src_ext = self._get_ext_from_mime(source_asset.mime_type)
            src_tmp = os.path.join(tmpdir, f"source.{src_ext}")
            dst_tmp = os.path.join(tmpdir, f"{clip_id}.mp3")

            with open(src_tmp, "wb") as f:
                f.write(source_bytes)

            cmd = [
                "ffmpeg",
                "-y",
                "-ss", str(start_sec),
                "-i", src_tmp,
                "-t", str(dur_sec),
                "-vn",
                "-acodec", "libmp3lame",
                "-ar", "44100",
                "-ac", "2",
                "-b:a", "128k",
                dst_tmp,
            ]

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()

                if proc.returncode != 0 or not os.path.exists(dst_tmp) or os.path.getsize(dst_tmp) == 0:
                    if settings.ENVIRONMENT != "production":
                        with open(dst_tmp, "wb") as f:
                            f.write(source_bytes)
                    else:
                        err_msg = stderr.decode("utf-8", errors="ignore") if stderr else "Unknown ffmpeg error"
                        logger.error("media.clip.ffmpeg_failed", error=err_msg)
                        raise RuntimeError(f"Failed to generate cropped audio clip: {err_msg}")
            except FileNotFoundError:
                if settings.ENVIRONMENT != "production":
                    with open(dst_tmp, "wb") as f:
                        f.write(source_bytes)
                else:
                    raise

            with open(dst_tmp, "rb") as f:
                cropped_bytes = f.read()

        # Upload cropped mp3 to InsForge storage
        await self._upload_to_insforge(clip_object_path, cropped_bytes, "audio/mpeg")

        clip = DerivedAudioClip(
            id=clip_id,
            user_id=user_id,
            source_asset_id=source_asset_id,
            storage_path=clip_object_path,
            start_ms=start_ms,
            end_ms=end_ms,
            duration_ms=clip_duration_ms,
            purpose=purpose,
            label=label,
            transcript_excerpt=transcript_excerpt,
            coach_note=coach_note,
            expires_at=source_asset.expires_at,
            created_at=utcnow(),
        )
        db.add(clip)
        await db.commit()
        await db.refresh(clip)

        logger.info(
            "media.clip.created",
            clip_id=clip_id,
            user_id=user_id,
            storage="insforge",
            path=clip_object_path,
            start_ms=start_ms,
            end_ms=end_ms,
            duration_ms=clip_duration_ms,
        )
        return clip

    async def get_clip_bytes(
        self,
        db: AsyncSession,
        user_id: str,
        clip_id: str,
    ) -> Optional[Tuple[bytes, str]]:
        stmt = select(DerivedAudioClip).where(DerivedAudioClip.id == clip_id, DerivedAudioClip.user_id == user_id)
        res = await db.execute(stmt)
        clip = res.scalar_one_or_none()
        if not clip:
            logger.warning("media.clip.unauthorized_or_missing", clip_id=clip_id, user_id=user_id)
            return None

        if self._is_expired(clip.expires_at):
            logger.info("media.clip.expired", clip_id=clip_id)
            return None

        data = await self._download_from_insforge(clip.storage_path)
        if not data:
            logger.error("media.clip.missing_in_insforge", clip_id=clip_id, path=clip.storage_path)
            return None

        mime = "audio/mpeg" if clip.storage_path.endswith(".mp3") else "audio/webm"
        return data, mime

    async def cleanup_expired_assets(self, db: AsyncSession) -> int:
        now = utcnow()
        stmt = select(MediaAsset).where(MediaAsset.expires_at != None, MediaAsset.expires_at < now)
        res = await db.execute(stmt)
        expired_assets = list(res.scalars().all())

        count = 0
        for asset in expired_assets:
            try:
                await self._delete_from_insforge(asset.storage_path)
            except Exception as e:
                logger.warning("media.cleanup.insforge_delete_failed", path=asset.storage_path, error=str(e))
            await db.delete(asset)
            count += 1

        # Cleanup orphaned clips
        stmt_clips = select(DerivedAudioClip).where(DerivedAudioClip.expires_at != None, DerivedAudioClip.expires_at < now)
        res_clips = await db.execute(stmt_clips)
        for clip in res_clips.scalars().all():
            try:
                await self._delete_from_insforge(clip.storage_path)
            except Exception as e:
                pass
            await db.delete(clip)

        await db.commit()
        if count > 0:
            logger.info("media.cleanup.completed", expired_count=count)
        return count


# Canonical singleton media storage
media_storage: MediaStorageService = InsForgeMediaStorageService()
