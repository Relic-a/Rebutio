import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.db import CoachMessage, CoachThread, CoachingMemoryItem, MediaAsset, User
from backend.app.models.schemas import (
    CoachOpeningAnalysisResult,
    CoachTurnResponse,
    DebateReviewerResult,
)
from backend.app.services.ai.config import AICompletionResult
from backend.app.services.ai.gateway import ai_gateway
from backend.app.services.media.storage import media_storage

client = TestClient(app)


@pytest.mark.asyncio
async def test_media_storage_and_clip_cropping():
    from backend.app.persistence.db import async_session_factory
    from backend.app.persistence.repositories import UserRepository

    async with async_session_factory() as db:
        user_repo = UserRepository(db)
        user = await user_repo.get_or_create_user("test-user-media-1")

        # 1. Save media asset
        fake_wav = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        asset = await media_storage.save_media_asset(
            db=db,
            user_id=user.id,
            audio_bytes=fake_wav,
            mime_type="audio/wav",
            source_type="debate_turn",
            transcript="I believe this policy will improve public welfare.",
            duration_ms=4500,
        )

        assert asset.id.startswith("asset-")
        assert asset.user_id == user.id
        assert asset.duration_ms == 4500

        # 2. Retrieve media bytes
        res = await media_storage.get_media_bytes(db=db, user_id=user.id, asset_id=asset.id)
        assert res is not None
        retrieved_bytes, mime = res
        assert retrieved_bytes == fake_wav
        assert mime == "audio/wav"

        # 3. Create derived clip (mocked ffmpeg execution)
        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value.returncode = 0
            mock_sub.return_value.stdout = fake_wav

            clip = await media_storage.create_derived_clip(
                db=db,
                user_id=user.id,
                source_asset_id=asset.id,
                start_ms=500,
                end_ms=3000,
                purpose="coach_feedback",
                label="Debate · Turn 1",
                transcript_excerpt="improve public welfare",
                coach_note="Notice the steady delivery when making your key point.",
            )

            assert clip.id.startswith("clip-")
            assert clip.source_asset_id == asset.id
            assert clip.start_ms == 500
            assert clip.end_ms == 3000
            assert clip.duration_ms == 2500


from backend.app.api.dependencies import sign_user_id

@pytest.mark.asyncio
async def test_coach_home_and_session_thread_flow():
    cookie_val = sign_user_id("test-user-coach-1")
    cookies = {"rebutio_session": cookie_val}

    # 1. Request Coach Home
    res = client.get("/api/coach/home", cookies=cookies)
    assert res.status_code == 200
    data = res.json()
    assert "activeFocus" in data
    assert "progressSummary" in data
    assert "presetQuestions" in data
    assert len(data["presetQuestions"]) >= 4

    # 2. Create general coach thread
    res_gen = client.post(
        "/api/coach/threads",
        json={"text": "How can I make my refutations punchier?"},
        cookies=cookies,
    )
    assert res_gen.status_code == 200
    gen_data = res_gen.json()
    assert gen_data["thread"]["threadType"] == "general"
    assert len(gen_data["messages"]) >= 2
    assert gen_data["messages"][0]["sender"] == "user"
    assert gen_data["messages"][1]["sender"] == "coach"

    thread_id = gen_data["thread"]["id"]

    # 3. Send follow-up message to coach
    res_msg = client.post(
        f"/api/coach/threads/{thread_id}/messages",
        json={"text": "Give me a quick 1-sentence template."},
        cookies=cookies,
    )
    assert res_msg.status_code == 200
    msg_data = res_msg.json()
    assert msg_data["sender"] == "coach"
    assert len(msg_data["text"]) > 10

    # 4. User memory correction
    res_corr = client.post(
        "/api/coach/memory/correction",
        json={
            "patternType": "delivery_pattern",
            "label": "Hesitation in opening",
            "correctionText": "I was actually pausing deliberately to organize thoughts, not hesitating.",
            "action": "update",
        },
        cookies=cookies,
    )
    assert res_corr.status_code == 200
    assert res_corr.json()["success"] is True


@pytest.mark.asyncio
async def test_coach_audio_single_user_message_and_tool_loop():
    from backend.app.persistence.db import async_session_factory
    from backend.app.services.coach.engine import CoachEngine
    from backend.app.persistence.repositories import CoachRepository, UserRepository

    async with async_session_factory() as db:
        user_repo = UserRepository(db)
        coach_repo = CoachRepository(db)
        user = await user_repo.get_or_create_user("test-user-tool-loop")

        # 1. Create a general coach thread
        thread = await coach_repo.create_general_thread(user.id, "Pronunciation Analysis")

        # 2. Save a media asset with phonemes
        fake_wav = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        asset = await media_storage.save_media_asset(
            db=db,
            user_id=user.id,
            audio_bytes=fake_wav,
            mime_type="audio/wav",
            source_type="coach_audio",
            transcript="I am testing the phoneme tool call flow.",
            phonemes=[{"phone": "AY", "start_ms": 100, "end_ms": 300}, {"phone": "M", "start_ms": 300, "end_ms": 500}],
            speech_metrics={"words_per_minute": 135, "pause_count": 0},
            duration_ms=2000,
        )

        # 3. Test text message with get_phoneme_data tool loop
        with patch.object(ai_gateway, "_execute_structured_completion") as mock_complete:
            # First completion requests get_phoneme_data
            first_resp = CoachTurnResponse(
                reply_text="Let me inspect the acoustic phoneme alignment of that utterance.",
                requested_tool="get_phoneme_data",
                tool_args={"media_asset_id": asset.id},
                evidence_card=None,
                quick_replies=["How can I improve it?"],
                memory_update=None,
            )
            # Follow-up completion provides feedback incorporating phoneme results
            second_resp = CoachTurnResponse(
                reply_text="Your /AY/ sound in 'I' was sustained for 200ms with clear articulation.",
                requested_tool=None,
                tool_args=None,
                evidence_card=None,
                quick_replies=["Practice again"],
                memory_update=None,
            )
            mock_complete.side_effect = [first_resp, second_resp]

            coach_msg = await CoachEngine.process_user_text_message(
                db=db,
                user_id=user.id,
                thread_id=thread.id,
                text="How did my pronunciation of the opening word sound?",
                media_asset_id=asset.id,
            )

            assert coach_msg.sender == "coach"
            assert "200ms" in coach_msg.text
            assert mock_complete.call_count == 2

        # 4. Test audio message creates exactly ONE user message
        with patch.object(ai_gateway, "transcribe_audio", AsyncMock(return_value="Testing audio message creation")), \
             patch.object(CoachEngine, "process_user_text_message") as mock_proc_text:
            
            mock_proc_text.return_value = CoachEngine._message_to_schema(
                CoachMessage(
                    id="mock-coach-reply",
                    thread_id=thread.id,
                    user_id=user.id,
                    sender="coach",
                    message_type="text",
                    processing_state="ready",
                )
            )

            msg_count_before = len(await coach_repo.get_thread_messages(thread.id))
            user_schema, coach_schema = await CoachEngine.process_user_audio_message(
                db=db,
                user_id=user.id,
                thread_id=thread.id,
                audio_bytes=fake_wav,
                mime_type="audio/wav",
            )

            messages_after = await coach_repo.get_thread_messages(thread.id)
            user_messages_added = [m for m in messages_after[msg_count_before:] if m.sender == "user"]
            # Assert exactly 1 user message was added!
            assert len(user_messages_added) == 1
            assert user_messages_added[0].message_type == "audio"
            # Assert process_user_text_message was called with create_user_message=False
            mock_proc_text.assert_called_once()
            _, kwargs = mock_proc_text.call_args
            assert kwargs.get("create_user_message") is False
