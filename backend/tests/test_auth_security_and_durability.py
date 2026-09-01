import pytest
import uuid
from httpx import ASGITransport, AsyncClient

from backend.app.api.dependencies import create_test_auth_token, sign_user_id
from backend.app.config import settings
from backend.app.main import app, lifespan
from backend.app.models.db import CoachMemory
from backend.app.persistence.db import async_session_factory, init_db
from backend.app.persistence.repositories import (
    CoachRepository,
    DebateSessionRepository,
)
from backend.app.services.media.storage import media_storage


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_auth_fail_closed_without_bypass(monkeypatch):
    """
    Verifies that when ALLOW_DEV_AUTH_BYPASS is False, any request without a
    valid verified Bearer JWT is strictly rejected with 401 Unauthorized.
    """
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH_BYPASS", False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Unauthenticated request without Authorization header
        resp = await client.get("/api/bootstrap")
        assert resp.status_code == 401
        assert "Missing or invalid authentication token" in resp.json()["detail"]

        # Request with raw user ID instead of token
        resp_user_header = await client.get("/api/bootstrap", headers={"X-InsForge-User": "some-user-id"})
        assert resp_user_header.status_code == 401

        # Request with valid signed JWT Bearer token
        valid_user_id = f"user-auth-test-{uuid.uuid4().hex[:8]}"
        token = create_test_auth_token(valid_user_id)
        resp_auth = await client.get("/api/bootstrap", headers={"Authorization": f"Bearer {token}"})
        assert resp_auth.status_code == 200
        assert resp_auth.json()["onboarded"] is False


@pytest.mark.asyncio
async def test_production_startup_security_guardrails(monkeypatch):
    """
    Verifies that the backend fails closed on startup if deployed in production with:
    - ALLOW_DEV_AUTH_BYPASS enabled
    - Default dev data encryption key
    - Default dev session secret
    """
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    # 1. Refuse startup if ALLOW_DEV_AUTH_BYPASS is True in production
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH_BYPASS", True)
    with pytest.raises(RuntimeError, match="ALLOW_DEV_AUTH_BYPASS cannot be True in production"):
        async with lifespan(app):
            pass

    # 2. Refuse startup if default encryption key is used in production
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH_BYPASS", False)
    monkeypatch.setattr(settings, "REBUTIO_DATA_ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
    with pytest.raises(RuntimeError, match="REBUTIO_DATA_ENCRYPTION_KEY must be configured"):
        async with lifespan(app):
            pass

    # 3. Refuse startup if default session secret is used in production
    monkeypatch.setattr(settings, "REBUTIO_DATA_ENCRYPTION_KEY", "custom-prod-encryption-key-32b-length!!")
    monkeypatch.setattr(settings, "REBUTIO_SESSION_SECRET", "rebutio-stable-dev-session-secret-key-32b")
    with pytest.raises(RuntimeError, match="REBUTIO_SESSION_SECRET must be configured"):
        async with lifespan(app):
            pass


@pytest.mark.asyncio
async def test_insforge_media_storage_lifecycle():
    """
    Verifies saving media assets, retrieving audio bytes, and generating derived clips
    via InsForgeMediaStorageService with private storage bucket paths.
    """
    user_id = f"user-media-{uuid.uuid4().hex[:8]}"
    dummy_wav = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"

    async with async_session_factory() as db:
        # Save media asset
        asset = await media_storage.save_media_asset(
            db=db,
            user_id=user_id,
            audio_bytes=dummy_wav,
            mime_type="audio/wav",
            source_type="debate_turn",
            duration_ms=2000,
        )
        assert asset.id.startswith("asset-")
        assert asset.user_id == user_id
        assert asset.storage_path.startswith(f"{user_id}/")

        # Retrieve media bytes
        res = await media_storage.get_media_bytes(db, user_id, asset.id)
        assert res is not None
        retrieved_bytes, mime = res
        assert retrieved_bytes == dummy_wav
        assert mime == "audio/wav"

        # Unauthorized access from another user must return None
        res_unauthorized = await media_storage.get_media_bytes(db, "other-user", asset.id)
        assert res_unauthorized is None


@pytest.mark.asyncio
async def test_manual_finish_and_submission_status_enforcement():
    """
    Verifies that:
    1. Manual finish sets session status to finished immediately.
    2. Finished / non-active sessions reject new turn submissions with 400.
    """
    user_id = f"user-finish-test-{uuid.uuid4().hex[:8]}"
    token = create_test_auth_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Start a debate
        start_resp = await client.post("/api/debates/start", json={"side": "agree", "onboarding": True}, headers=headers)
        assert start_resp.status_code == 200
        session_id = start_resp.json()["session"]["id"]

        # Submit Turn 1
        t1_resp = await client.post(
            f"/api/sessions/{session_id}/turns",
            data={"transcript": "Initial claim for turn 1", "turn_index": 1},
            headers=headers,
        )
        assert t1_resp.status_code == 200

        # Manually finish session
        finish_resp = await client.post(f"/api/sessions/{session_id}/finish", headers=headers)
        assert finish_resp.status_code == 200

        # Verify session is marked finished in DB
        async with async_session_factory() as db:
            sess_repo = DebateSessionRepository(db)
            sess = await sess_repo.get_session(session_id)
            assert sess.status == "finished"

        # Attempting to submit another turn on finished session must fail with 400
        turn_after_finish = await client.post(
            f"/api/sessions/{session_id}/turns",
            data={"transcript": "Another turn after finish", "turn_index": 2},
            headers=headers,
        )
        assert turn_after_finish.status_code == 400
        assert "not active" in turn_after_finish.json()["detail"]


@pytest.mark.asyncio
async def test_coach_memory_optimistic_concurrency():
    """
    Verifies that CoachRepository.save_memory_markdown uses optimistic concurrency
    based on expected_revision and handles concurrent updates cleanly.
    """
    user_id = f"user-concurrency-{uuid.uuid4().hex[:8]}"

    async with async_session_factory() as db:
        repo = CoachRepository(db)

        # Initial save (revision 1)
        initial_md = "# Initial Memory\n- Point 1"
        rev1 = await repo.save_memory_markdown(user_id, initial_md, expected_revision=0)
        assert rev1 == 1

        # Second update with matching expected revision (revision 2)
        second_md = "# Updated Memory\n- Point 2"
        rev2 = await repo.save_memory_markdown(user_id, second_md, expected_revision=1)
        assert rev2 == 2

        # Stale update with mismatched expected_revision (simulating simultaneous update)
        # Should detect conflict and retry
        stale_md = "# Stale Update Overwrite\n- Point Stale"
        rev3 = await repo.save_memory_markdown(user_id, stale_md, expected_revision=1)
        assert rev3 == 3

        loaded_md, final_rev = await repo.get_memory_markdown(user_id)
        assert final_rev == 3
        assert "Stale Update Overwrite" in loaded_md
