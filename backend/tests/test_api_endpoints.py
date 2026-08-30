import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

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
