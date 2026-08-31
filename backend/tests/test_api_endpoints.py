import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.api.dependencies import sign_user_id
from backend.app.main import app
from backend.app.persistence.db import init_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_health_and_ready():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

        resp_ready = await client.get("/ready")
        assert resp_ready.status_code == 200
        assert resp_ready.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_bootstrap_and_onboarding_flow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Bootstrap
        resp = await client.get("/api/bootstrap")
        assert resp.status_code == 200
        data = resp.json()
        assert data["onboarded"] is False
        assert "path" in data
        assert len(data["path"]["nodes"]) == 11

        # 2. Save Onboarding Preferences
        prefs = {
            "goals": ["Sound clearer", "Think faster in English"],
            "comfort": "I can hold conversations",
            "interests": ["tech", "money", "society"],
            "intensity": "balanced",
        }
        resp_pref = await client.post("/api/onboarding/preferences", json=prefs)
        assert resp_pref.status_code == 200

        # 3. Start Onboarding Spar
        resp_spar = await client.post("/api/onboarding/spar/start?side=agree")
        assert resp_spar.status_code == 200
        spar_data = resp_spar.json()
        assert "session" in spar_data
        assert spar_data["session"]["totalUserTurns"] == 3
        session_id = spar_data["session"]["id"]

        # 4. Submit Turn 1 (with audio simulation)
        turn1_resp = await client.post(
            f"/api/sessions/{session_id}/turns",
            data={"transcript": "Social media makes people interact superficially.", "client_response_delay_ms": 1200},
        )
        assert turn1_resp.status_code == 200
        t1_data = turn1_resp.json()
        assert t1_data["userTurn"]["text"] == "Social media makes people interact superficially."
        assert t1_data["opponentTurn"]["speaker"] == "opponent"
        assert t1_data["finished"] is False
        assert t1_data["nextUserTurnNumber"] == 2

        # 5. Submit Turn 2 (Penultimate Turn)
        turn2_resp = await client.post(
            f"/api/sessions/{session_id}/turns",
            data={"transcript": "Convenience is not the same as genuine companionship.", "client_response_delay_ms": 1800},
        )
        assert turn2_resp.status_code == 200
        t2_data = turn2_resp.json()
        assert t2_data["finished"] is False
        assert t2_data["nextUserTurnNumber"] == 3

        # 6. Submit Turn 3 (Final Turn)
        turn3_resp = await client.post(
            f"/api/sessions/{session_id}/turns",
            data={"transcript": "In conclusion, depth requires presence which screens cannot substitute.", "client_response_delay_ms": 900},
        )
        assert turn3_resp.status_code == 200
        t3_data = turn3_resp.json()
        assert t3_data["finished"] is True

        # 7. Get Review
        review_resp = await client.get(f"/api/sessions/{session_id}/review")
        assert review_resp.status_code == 200
        rev = review_resp.json()
        assert rev["stars"]["completed"] is True
        assert rev["stars"]["stars"] >= 1  # Star 1 deterministic completion rule
        assert "argumentFeedback" in rev
        assert "languageFeedback" in rev
        assert rev["xpEarned"] > 0

        # 8. Submit Review Disagreement Feedback
        feedback_resp = await client.post(
            f"/api/sessions/{session_id}/review-feedback",
            json={"sessionId": session_id, "verdict": "disagree", "reason": "Felt my final analogy was stronger."},
        )
        assert feedback_resp.status_code == 200

        # 9. Get Progress
        prog_resp = await client.get("/api/progress")
        assert prog_resp.status_code == 200
        prog_data = prog_resp.json()
        assert prog_data["debatesCompleted"] >= 1
        assert prog_data["xp"] > 0

        # 10. Get Debate Choices
        choices_resp = await client.get("/api/debates/choices")
        assert choices_resp.status_code == 200
        assert len(choices_resp.json()) > 0

        # 11. Settings & Privacy
        settings_resp = await client.patch(
            "/api/settings",
            json={"saveTranscripts": True, "captionsEnabled": True, "intensity": "bring_it_on"},
        )
        assert settings_resp.status_code == 200
        assert settings_resp.json()["saveTranscripts"] is True
        assert settings_resp.json()["intensity"] == "bring_it_on"

        # 12. History List & Deletion
        history_resp = await client.get("/api/settings/history")
        assert history_resp.status_code == 200
        history_items = history_resp.json()
        assert len(history_items) >= 1
        assert history_items[0]["sessionId"] == session_id

        del_hist_resp = await client.delete("/api/settings/history")
        assert del_hist_resp.status_code == 200
        assert del_hist_resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_path_debate_topic_assignment_stays_stable_after_start():
    user_id = "topic-assignment-regression-user"
    headers = {"X-User-ID-Signed": sign_user_id(user_id)}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers=headers,
    ) as client:
        choices = (await client.get("/api/debates/choices")).json()
        assert choices

        first_path = (await client.get("/api/path")).json()
        current = next(node for node in first_path["nodes"] if node["status"] == "current")
        assert current["topicId"]
        assert current["topicPreview"]

        started = await client.post(
            "/api/debates/start",
            json={"topicId": current["topicId"], "side": "agree"},
        )
        assert started.status_code == 200
        assert started.json()["session"]["topic"] == current["topicPreview"]

        second_path = (await client.get("/api/path")).json()
        current_again = next(
            node for node in second_path["nodes"] if node["status"] == "current"
        )
        assert current_again["topicId"] == current["topicId"]
        assert current_again["topicPreview"] == current["topicPreview"]


@pytest.mark.asyncio
async def test_oversized_audio_upload_rejection():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/debates/start", json={"side": "agree"})
        session_id = resp.json()["session"]["id"]

        # Create dummy oversized payload (> 25MB)
        oversized_payload = b"0" * (26 * 1024 * 1024)
        files = {"audio": ("huge.webm", oversized_payload, "audio/webm")}

        turn_resp = await client.post(
            f"/api/sessions/{session_id}/turns",
            files=files,
        )
        assert turn_resp.status_code == 400
        assert "25MB" in turn_resp.json()["detail"]


@pytest.mark.asyncio
async def test_empty_transcription_returns_422_with_mic_check_message(monkeypatch):
    from backend.app.services.ai.gateway import ai_gateway

    async def mock_empty_stt(*args, **kwargs):
        return ""

    monkeypatch.setattr(ai_gateway, "transcribe_audio", mock_empty_stt)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/debates/start", json={"side": "agree"})
        session_id = resp.json()["session"]["id"]

        dummy_audio = b"RIFFfakeaudiobytes"
        files = {"audio": ("turn.webm", dummy_audio, "audio/webm")}

        turn_resp = await client.post(
            f"/api/sessions/{session_id}/turns",
            files=files,
        )
        assert turn_resp.status_code == 422
        detail = turn_resp.json()["detail"]
        assert "No speech detected" in detail
        assert "microphone" in detail.lower()


@pytest.mark.asyncio
async def test_empty_submission_without_audio_or_text_returns_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/debates/start", json={"side": "agree"})
        session_id = resp.json()["session"]["id"]

        turn_resp = await client.post(
            f"/api/sessions/{session_id}/turns",
            data={},
        )
        assert turn_resp.status_code == 422
        assert "No speech detected" in turn_resp.json()["detail"]

