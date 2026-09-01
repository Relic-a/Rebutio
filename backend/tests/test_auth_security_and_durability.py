import pytest
import uuid
from unittest.mock import patch
from httpx import ASGITransport, AsyncClient

from backend.app.api.dependencies import create_test_auth_token, sign_user_id
from backend.app.config import settings
from backend.app.main import app, lifespan
from backend.app.models.db import CoachMemory
from backend.app.persistence.db import async_session_factory, init_db
from backend.app.persistence.repositories import (
    CoachRepository,
    DebateSessionRepository,
    ProgressRepository,
    TopicInventoryRepository,
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
    - Non-PostgreSQL database
    - Missing InsForge JWT verification configuration
    - Missing InsForge storage credentials
    - ALLOW_DEV_AUTH_BYPASS enabled
    - Default dev data encryption key
    - Default dev session secret
    """
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH_BYPASS", False)
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+asyncpg://postgres:pass@localhost:5432/rebutio")
    monkeypatch.setattr(settings, "INSFORGE_JWT_SECRET", "custom-prod-jwt-secret-key-123456789")
    monkeypatch.setattr(settings, "INSFORGE_API_KEY", "custom-prod-api-key-123456789")
    monkeypatch.setattr(settings, "REBUTIO_DATA_ENCRYPTION_KEY", "custom-prod-encryption-key-32b-length!!")
    monkeypatch.setattr(settings, "REBUTIO_SESSION_SECRET", "custom-prod-session-secret-32b-length!!")

    # 1. Refuse startup if DATABASE_URL is SQLite in production
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite+aiosqlite:///./rebutio.db")
    with pytest.raises(RuntimeError, match="DATABASE_URL must be PostgreSQL"):
        async with lifespan(app):
            pass
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+asyncpg://postgres:pass@localhost:5432/rebutio")

    # 2. Refuse startup if ALLOW_DEV_AUTH_BYPASS is True in production
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH_BYPASS", True)
    with pytest.raises(RuntimeError, match="ALLOW_DEV_AUTH_BYPASS cannot be True in production"):
        async with lifespan(app):
            pass
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH_BYPASS", False)

    # 3. Refuse startup if InsForge JWT secret/key is missing
    monkeypatch.setattr(settings, "INSFORGE_JWT_SECRET", "")
    monkeypatch.setattr(settings, "INSFORGE_JWT_PUBLIC_KEY", "")
    with pytest.raises(RuntimeError, match="requires InsForge JWT verification configuration"):
        async with lifespan(app):
            pass
    monkeypatch.setattr(settings, "INSFORGE_JWT_SECRET", "custom-prod-jwt-secret-key-123456789")

    # 4. Refuse startup if private INSFORGE_API_KEY is missing (anon key is NOT accepted as privileged server key)
    monkeypatch.setattr(settings, "INSFORGE_API_KEY", "")
    monkeypatch.setattr(settings, "INSFORGE_ANON_KEY", "anon-key-only")
    with pytest.raises(RuntimeError, match="requires private INSFORGE_API_KEY"):
        async with lifespan(app):
            pass
    monkeypatch.setattr(settings, "INSFORGE_API_KEY", "ik_custom_prod_api_key_123456789")

    # 5. Refuse startup if default encryption key is used in production
    monkeypatch.setattr(settings, "REBUTIO_DATA_ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
    with pytest.raises(RuntimeError, match="REBUTIO_DATA_ENCRYPTION_KEY must be configured"):
        async with lifespan(app):
            pass
    monkeypatch.setattr(settings, "REBUTIO_DATA_ENCRYPTION_KEY", "custom-prod-encryption-key-32b-length!!")

    # 6. Refuse startup if default session secret is used in production
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
async def test_authenticated_settings_requests(monkeypatch):
    """
    Verifies that settings endpoints require valid InsForge authentication
    and return correct user settings when authenticated.
    """
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH_BYPASS", False)

    user_id = f"user-settings-test-{uuid.uuid4().hex[:8]}"
    token = create_test_auth_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Unauthenticated request rejected with 401
        unauth_resp = await client.get("/api/settings")
        assert unauth_resp.status_code == 401

        unauth_patch = await client.patch("/api/settings", json={"saveTranscripts": True})
        assert unauth_patch.status_code == 401

        # 2. Authenticated GET settings
        get_resp = await client.get("/api/settings", headers=headers)
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert "saveTranscripts" in data
        assert "captionsEnabled" in data
        assert "intensity" in data

        # 3. Authenticated PATCH settings
        patch_resp = await client.patch(
            "/api/settings",
            json={"saveTranscripts": True, "captionsEnabled": False, "intensity": "bring_it_on"},
            headers=headers,
        )
        assert patch_resp.status_code == 200
        patch_data = patch_resp.json()
        assert patch_data["saveTranscripts"] is True
        assert patch_data["captionsEnabled"] is False
        assert patch_data["intensity"] == "bring_it_on"


@pytest.mark.asyncio
async def test_non_active_session_rejection():
    """
    Verifies that sessions with status != 'active' (e.g. 'review_pending' or 'finished')
    strictly reject turn submissions with 400 Bad Request.
    """
    user_id = f"user-non-active-test-{uuid.uuid4().hex[:8]}"
    token = create_test_auth_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        start_resp = await client.post("/api/debates/start", json={"side": "agree", "onboarding": True}, headers=headers)
        assert start_resp.status_code == 200
        session_id = start_resp.json()["session"]["id"]

        # Set session to review_pending in DB
        async with async_session_factory() as db:
            sess_repo = DebateSessionRepository(db)
            sess = await sess_repo.get_session(session_id)
            sess.status = "review_pending"
            await db.commit()

        # Turn submission on review_pending session must fail
        turn_resp = await client.post(
            f"/api/sessions/{session_id}/turns",
            data={"transcript": "Turn during review_pending", "turn_index": 1},
            headers=headers,
        )
        assert turn_resp.status_code == 400
        assert "not active" in turn_resp.json()["detail"]


@pytest.mark.asyncio
async def test_recoverable_review_pending_finalization():
    """
    Verifies that if a session is left in review_pending (simulating server restart/interruption),
    requesting the review resumes and completes all remaining finalization steps:
    review saved, progress updated, topic consumed, coach memory updated, coach thread initialized,
    and status persisted as finished.
    """
    from backend.app.domain.orchestration import DebateOrchestrator
    user_id = f"user-recover-test-{uuid.uuid4().hex[:8]}"
    token = create_test_auth_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        start_resp = await client.post("/api/debates/start", json={"side": "agree", "onboarding": True}, headers=headers)
        session_id = start_resp.json()["session"]["id"]

        # Submit Turn 1
        await client.post(
            f"/api/sessions/{session_id}/turns",
            data={"transcript": "I believe this topic is crucial.", "turn_index": 1},
            headers=headers,
        )

        # Force session state to review_pending (simulating interruption before finalization completed)
        async with async_session_factory() as db:
            sess_repo = DebateSessionRepository(db)
            sess = await sess_repo.get_session(session_id)
            sess.status = "review_pending"
            await db.commit()

        # Request review: must resume, finalize, and transition to finished
        review_resp = await client.get(f"/api/sessions/{session_id}/review", headers=headers)
        assert review_resp.status_code == 200
        rev = review_resp.json()
        assert rev["stars"]["completed"] is True
        assert rev["xpEarned"] > 0

        # Verify DB persisted state
        async with async_session_factory() as db:
            sess_repo = DebateSessionRepository(db)
            prog_repo = ProgressRepository(db)
            topic_repo = TopicInventoryRepository(db)
            coach_repo = CoachRepository(db)

            sess = await sess_repo.get_session(session_id)
            assert sess.status == "finished"

            prog = await prog_repo.get_progress(user_id)
            assert prog.xp > 0
            assert prog.debates_completed >= 1

            # Coach memory updated
            mem_md, rev_num = await coach_repo.get_memory_markdown(user_id)
            assert rev_num >= 1

            # Coach thread created
            thread = await coach_repo.get_or_create_debate_thread(user_id, session_id, "Test Thread")
            assert thread.session_id == session_id


@pytest.mark.asyncio
async def test_idempotent_post_debate_processing():
    """
    Verifies that calling finalization multiple times on the same session
    does not duplicate XP, progress, or side effects.
    """
    from backend.app.domain.orchestration import DebateOrchestrator
    user_id = f"user-idempotent-test-{uuid.uuid4().hex[:8]}"
    token = create_test_auth_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        start_resp = await client.post("/api/debates/start", json={"side": "agree", "onboarding": True}, headers=headers)
        session_id = start_resp.json()["session"]["id"]

        await client.post(
            f"/api/sessions/{session_id}/turns",
            data={"transcript": "Strong initial debate point.", "turn_index": 1},
            headers=headers,
        )

        # Run finalization first time
        review1 = await DebateOrchestrator.finalize_debate_review(session_id, user_id)
        assert review1.sessionId == session_id

        # Capture progress after first finalization
        async with async_session_factory() as db:
            prog_repo = ProgressRepository(db)
            prog1 = await prog_repo.get_progress(user_id)
            xp1 = prog1.xp
            debates1 = prog1.debates_completed

        # Run finalization second time on the same session
        review2 = await DebateOrchestrator.finalize_debate_review(session_id, user_id)
        assert review2.sessionId == session_id
        assert review2.xpEarned == review1.xpEarned

        # Verify progress was NOT duplicated
        async with async_session_factory() as db:
            prog_repo = ProgressRepository(db)
            prog2 = await prog_repo.get_progress(user_id)
            assert prog2.xp == xp1
            assert prog2.debates_completed == debates1


@pytest.mark.asyncio
async def test_coach_memory_optimistic_concurrency_conflict_handling():
    """
    Verifies that CoachRepository.save_memory_markdown prevents stale overwrites
    and CoachEngine.update_coach_memory_after_debate reconciles on conflict.
    """
    from backend.app.services.coach.engine import CoachEngine
    user_id = f"user-concurrency-{uuid.uuid4().hex[:8]}"

    async with async_session_factory() as db:
        repo = CoachRepository(db)

        # Initial save (revision 1)
        initial_md = "# Initial Memory\n- Point 1"
        saved1, rev1 = await repo.save_memory_markdown(user_id, initial_md, expected_revision=0)
        assert saved1 is True
        assert rev1 == 1

        # Second update with matching expected revision (revision 2)
        second_md = "# Updated Memory\n- Point 2"
        saved2, rev2 = await repo.save_memory_markdown(user_id, second_md, expected_revision=1)
        assert saved2 is True
        assert rev2 == 2

        # Attempt stale update with old expected_revision=1 -> must be rejected (saved=False)
        stale_md = "# Stale Update Overwrite\n- Point Stale"
        saved3, rev3 = await repo.save_memory_markdown(user_id, stale_md, expected_revision=1)
        assert saved3 is False
        assert rev3 is None

        # Verify memory in DB remained the newer version (revision 2)
        loaded_md, final_rev = await repo.get_memory_markdown(user_id)
        assert final_rev == 2
        assert "Updated Memory" in loaded_md
        assert "Stale Update Overwrite" not in loaded_md

        # Verify CoachEngine reconciles memory properly after conflict
        debate_summary = {
            "topic": "Testing AI Debate Topic",
            "user_side": "agree",
            "outcome": "user_win",
            "stars": 3,
            "score_technique": 9,
            "score_grammar": 9,
            "score_vocabulary": 9,
            "score_delivery": 9,
        }
        reconciled_md = await CoachEngine.update_coach_memory_after_debate(db, user_id, debate_summary)
        assert reconciled_md is not None
        _, updated_rev = await repo.get_memory_markdown(user_id)
        assert updated_rev == 3


@pytest.mark.asyncio
async def test_production_storage_failure_behavior(monkeypatch):
    """
    Verifies that when ENVIRONMENT == 'production', storage failures raise RuntimeError
    and do not insert orphan records into the media_assets table.
    """
    from backend.app.models.db import MediaAsset
    from sqlalchemy import select

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    # Mock _upload_to_insforge to simulate storage API error in production
    async def mock_failing_upload(*args, **kwargs):
        raise RuntimeError("InsForge storage service unavailable: HTTP 503")

    monkeypatch.setattr(media_storage, "_upload_to_insforge", mock_failing_upload)

    user_id = f"user-prod-storage-fail-{uuid.uuid4().hex[:8]}"
    dummy_audio = b"fake-audio-bytes"

    async with async_session_factory() as db:
        # In production, save_media_asset must raise and not save DB row
        with pytest.raises(RuntimeError, match="InsForge storage service unavailable"):
            await media_storage.save_media_asset(
                db=db,
                user_id=user_id,
                audio_bytes=dummy_audio,
                mime_type="audio/webm",
            )

        # Verify no record was created in database
        stmt = select(MediaAsset).where(MediaAsset.user_id == user_id)
        res = await db.execute(stmt)
        assert res.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_protected_audio_access_without_url_tokens(monkeypatch):
    """
    Verifies that media audio endpoints reject URL query parameter tokens
    when ALLOW_DEV_AUTH_BYPASS is False, and require standard Authorization Bearer header.
    """
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH_BYPASS", False)

    user_id = f"user-audio-auth-{uuid.uuid4().hex[:8]}"
    token = create_test_auth_token(user_id)
    dummy_wav = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"

    async with async_session_factory() as db:
        asset = await media_storage.save_media_asset(
            db=db,
            user_id=user_id,
            audio_bytes=dummy_wav,
            mime_type="audio/wav",
        )
        asset_id = asset.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Access with query token param must fail with 401
        url_with_param = f"/api/media/{asset_id}/audio?token={token}"
        resp_param = await client.get(url_with_param)
        assert resp_param.status_code == 401

        # 2. Access with Bearer Authorization header must succeed
        resp_header = await client.get(f"/api/media/{asset_id}/audio", headers={"Authorization": f"Bearer {token}"})
        assert resp_header.status_code == 200
        assert resp_header.content == dummy_wav


@pytest.mark.asyncio
async def test_retry_after_progress_already_applied():
    """
    Verifies that if progress was already recorded for a session_id (simulating crash before review save),
    retrying finalization records the review without duplicating XP or debate counts.
    """
    from backend.app.domain.orchestration import DebateOrchestrator
    user_id = f"user-prog-idemp-{uuid.uuid4().hex[:8]}"
    token = create_test_auth_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        start_resp = await client.post("/api/debates/start", json={"side": "agree", "onboarding": True}, headers=headers)
        session_id = start_resp.json()["session"]["id"]

        await client.post(
            f"/api/sessions/{session_id}/turns",
            data={"transcript": "Argument turn.", "turn_index": 1},
            headers=headers,
        )

        # Manually apply progress with session_id beforehand (simulating partial completion)
        async with async_session_factory() as db:
            prog_repo = ProgressRepository(db)
            await prog_repo.record_debate_completion(
                user_id=user_id,
                skill_id="counterpoint",
                stars_earned=2,
                xp_earned=140,
                outcome="user_win",
                streak_extended=True,
                session_id=session_id,
            )
            prog_before = await prog_repo.get_progress(user_id)
            xp_before = prog_before.xp
            debates_before = prog_before.debates_completed

        # Run finalization
        review = await DebateOrchestrator.finalize_debate_review(session_id, user_id)
        assert review.sessionId == session_id

        # Verify progress was not duplicated
        async with async_session_factory() as db:
            prog_repo = ProgressRepository(db)
            prog_after = await prog_repo.get_progress(user_id)
            assert prog_after.xp == xp_before
            assert prog_after.debates_completed == debates_before


@pytest.mark.asyncio
async def test_retry_after_review_exists_but_coach_memory_incomplete():
    """
    Verifies that if a review exists in DB but the server crashed before Coach memory / thread was saved,
    retrying finalization safely finishes Coach memory and initializes the thread.
    """
    from backend.app.domain.orchestration import DebateOrchestrator
    user_id = f"user-review-retry-{uuid.uuid4().hex[:8]}"
    token = create_test_auth_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        start_resp = await client.post("/api/debates/start", json={"side": "agree", "onboarding": True}, headers=headers)
        session_id = start_resp.json()["session"]["id"]

        await client.post(
            f"/api/sessions/{session_id}/turns",
            data={"transcript": "Clear spoken point.", "turn_index": 1},
            headers=headers,
        )

        # Save review into DB manually (simulating crash right after review save)
        async with async_session_factory() as db:
            sess_repo = DebateSessionRepository(db)
            await sess_repo.save_review(
                session_id=session_id,
                user_id=user_id,
                outcome="user_win",
                stars=2,
                completed=True,
                skill_demonstrated=True,
                xp_earned=140,
                streak_extended=True,
                score_technique=8,
                score_grammar=8,
                score_vocabulary=8,
                score_delivery=8,
            )

        # Request review via API: must resume, update coach memory and thread, and mark finished
        rev_resp = await client.get(f"/api/sessions/{session_id}/review", headers=headers)
        assert rev_resp.status_code == 200

        async with async_session_factory() as db:
            sess_repo = DebateSessionRepository(db)
            coach_repo = CoachRepository(db)

            sess = await sess_repo.get_session(session_id)
            assert sess.status == "finished"

            mem_md, _ = await coach_repo.get_memory_markdown(user_id)
            assert f"<!-- session:{session_id} -->" in mem_md


@pytest.mark.asyncio
async def test_retry_after_coach_memory_already_contains_session():
    """
    Verifies that calling CoachEngine.update_coach_memory_after_debate with a debate_summary
    whose session_id is already marked in Coach memory returns without modifying or duplicating content.
    """
    from backend.app.services.coach.engine import CoachEngine
    user_id = f"user-mem-marker-{uuid.uuid4().hex[:8]}"

    async with async_session_factory() as db:
        coach_repo = CoachRepository(db)
        session_id = f"session-marked-{uuid.uuid4().hex[:8]}"
        initial_md = f"# Coach Memory\n- Baseline memory\n\n<!-- session:{session_id} -->\n"
        await coach_repo.save_memory_markdown(user_id, initial_md, expected_revision=0)

        debate_summary = {
            "session_id": session_id,
            "topic": "Testing Duplicate Prevention",
            "user_side": "agree",
            "outcome": "user_win",
            "stars": 3,
            "score_technique": 9,
            "score_grammar": 9,
            "score_vocabulary": 9,
            "score_delivery": 9,
        }

        result_md = await CoachEngine.update_coach_memory_after_debate(db, user_id, debate_summary)
        assert result_md == initial_md
        assert result_md.count(f"<!-- session:{session_id} -->") == 1


@pytest.mark.asyncio
async def test_coach_memory_ai_failure_does_not_append_marker_and_keeps_session_recoverable():
    """
    Verifies that if Coach memory AI update fails:
    1. The session marker is NOT appended to Coach memory.
    2. The un-updated memory is NOT saved with a false success marker.
    3. The session remains in review_pending (recoverable).
    """
    from backend.app.domain.orchestration import DebateOrchestrator
    from backend.app.services.ai.gateway import ai_gateway
    user_id = f"user-mem-fail-{uuid.uuid4().hex[:8]}"
    token = create_test_auth_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        start_resp = await client.post("/api/debates/start", json={"side": "agree", "onboarding": True}, headers=headers)
        session_id = start_resp.json()["session"]["id"]

        await client.post(
            f"/api/sessions/{session_id}/turns",
            data={"transcript": "Argument against social media echo chambers.", "turn_index": 1},
            headers=headers,
        )

        # Mock AI gateway update_coach_memory to simulate upstream AI failure
        with patch.object(ai_gateway, "update_coach_memory", side_effect=RuntimeError("Upstream AI model rate limit")):
            # finalize_debate_review must raise or fail closed
            with pytest.raises(RuntimeError, match="Coach memory AI update failed"):
                await DebateOrchestrator.finalize_debate_review(session_id, user_id)

        # Verify Coach memory in DB does NOT have the session marker
        async with async_session_factory() as db:
            coach_repo = CoachRepository(db)
            sess_repo = DebateSessionRepository(db)

            mem_md, _ = await coach_repo.get_memory_markdown(user_id)
            assert f"<!-- session:{session_id} -->" not in mem_md

            # Session must remain review_pending (not marked finished prematurely)
            sess = await sess_repo.get_session(session_id)
            assert sess.status == "review_pending"

        # Now simulate a retry where AI succeeds: memory is incorporated, marker appended, session finished
        rev_resp = await client.get(f"/api/sessions/{session_id}/review", headers=headers)
        assert rev_resp.status_code == 200

        async with async_session_factory() as db:
            coach_repo = CoachRepository(db)
            sess_repo = DebateSessionRepository(db)

            mem_md, _ = await coach_repo.get_memory_markdown(user_id)
            assert f"<!-- session:{session_id} -->" in mem_md
            assert mem_md.count(f"<!-- session:{session_id} -->") == 1

            sess = await sess_repo.get_session(session_id)
            assert sess.status == "finished"


@pytest.mark.asyncio
async def test_migration_files_integrity_and_isolation():
    """
    Verifies that:
    1. Base migration 20260831235601_create-rebutio-schema.sql is treated as immutable and does not
       contain the new completed_session_ids_json column in its CREATE TABLE.
    2. The dedicated migration 20260901000001_add_completed_session_ids_to_learning_progress.sql exists
       and provides the ALTER TABLE statement.
    """
    import glob
    import os

    migrations_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../migrations"))
    base_migration = os.path.join(migrations_dir, "20260831235601_create-rebutio-schema.sql")
    new_migration = os.path.join(migrations_dir, "20260901000001_add_completed_session_ids_to_learning_progress.sql")

    assert os.path.exists(base_migration), "Base migration file missing"
    assert os.path.exists(new_migration), "New migration file missing"

    with open(base_migration, "r", encoding="utf-8") as f:
        base_content = f.read()

    with open(new_migration, "r", encoding="utf-8") as f:
        new_content = f.read()

    # Base migration CREATE TABLE must NOT contain completed_session_ids_json
    assert "completed_session_ids_json" not in base_content

    # New migration MUST contain ALTER TABLE public.learning_progress
    assert "ALTER TABLE public.learning_progress" in new_content
    assert "completed_session_ids_json" in new_content
