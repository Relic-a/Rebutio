import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.app.persistence.db import init_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_session_resumability_and_turns():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Start a debate
        resp = await client.post("/api/debates/start", json={"side": "agree"})
        assert resp.status_code == 200
        sess_data = resp.json()["session"]
        session_id = sess_data["id"]

        # Submit Turn 1
        turn1_resp = await client.post(
            f"/api/sessions/{session_id}/turns",
            data={"transcript": "First premise.", "client_response_delay_ms": 1000},
        )
        assert turn1_resp.status_code == 200

        # Simulate browser refresh / reconnect: GET session
        resume_resp = await client.get(f"/api/sessions/{session_id}")
        assert resume_resp.status_code == 200
        resumed = resume_resp.json()
        assert resumed["id"] == session_id
        assert resumed["currentTurn"] == 2
        assert len(resumed["turns"]) == 2  # user turn + opponent turn
        assert resumed["turns"][0]["text"] == "First premise."
        assert resumed["turns"][1]["speaker"] == "opponent"


@pytest.mark.asyncio
async def test_privacy_transcript_deletion_when_saving_off():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Ensure transcript saving is OFF (default)
        await client.patch("/api/settings", json={"saveTranscripts": False})

        # Start 1-turn debate test or finish debate
        resp = await client.post("/api/debates/start", json={"side": "agree"})
        session_id = resp.json()["session"]["id"]

        # Submit turn
        await client.post(
            f"/api/sessions/{session_id}/turns",
            data={"transcript": "Sensitive user point.", "client_response_delay_ms": 500},
        )

        # Finish debate
        finish_resp = await client.post(f"/api/sessions/{session_id}/finish")
        assert finish_resp.status_code == 200

        # Get session: since saveTranscripts was False, turn text should be wiped
        sess_resp = await client.get(f"/api/sessions/{session_id}")
        assert sess_resp.status_code == 200
        for t in sess_resp.json()["turns"]:
            if t["speaker"] == "user":
                assert t["text"] is None  # Wiped for privacy!


@pytest.mark.asyncio
async def test_privacy_transcript_retention_when_saving_on():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Turn transcript saving ON
        await client.patch("/api/settings", json={"saveTranscripts": True})

        resp = await client.post("/api/debates/start", json={"side": "agree"})
        session_id = resp.json()["session"]["id"]

        await client.post(
            f"/api/sessions/{session_id}/turns",
            data={"transcript": "Retained user point.", "client_response_delay_ms": 500},
        )

        await client.post(f"/api/sessions/{session_id}/finish")

        sess_resp = await client.get(f"/api/sessions/{session_id}")
        assert sess_resp.status_code == 200
        user_turn = next(t for t in sess_resp.json()["turns"] if t["speaker"] == "user")
        assert user_turn["text"] == "Retained user point."  # Preserved encrypted!
