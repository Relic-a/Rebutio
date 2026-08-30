import asyncio
from typing import Optional
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user
from backend.app.domain.events import session_events
from backend.app.domain.orchestration import DebateOrchestrator
from backend.app.models.db import User
from backend.app.models.schemas import (
    DebateSessionSchema,
    DebateTurnSchema,
    SubmitTurnResponseSchema,
)
from backend.app.persistence.db import get_db
from backend.app.persistence.repositories import DebateSessionRepository
from backend.app.services.ai.gateway import ai_gateway
from backend.app.services.privacy.encryption import encryptor
from backend.app.services.tts.cache import tts_cache

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("/{session_id}", response_model=DebateSessionSchema)
async def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Session Resumability: returns active or completed session state with already-completed turns.
    """
    sess_repo = DebateSessionRepository(db)
    sess = await sess_repo.get_session(session_id)
    if not sess or sess.user_id != user.id:
        raise HTTPException(status_code=404, detail="Debate session not found")

    turn_schemas = []
    for t in sess.turns:
        txt = encryptor.decrypt_str(t.text_encrypted) if t.text_encrypted else None
        audio_url = f"/api/sessions/{session_id}/turns/{t.id}/audio" if t.speaker == "opponent" else None
        turn_schemas.append(
            DebateTurnSchema(
                id=t.id,
                speaker=t.speaker,
                text=txt,
                playback={"available": t.audio_available, "audioUrl": audio_url},
                durationSec=t.duration_sec,
            )
        )

    return DebateSessionSchema(
        id=sess.id,
        topic=sess.topic_text,
        skillTarget={"id": sess.skill_id, "name": sess.skill_name, "hint": sess.skill_hint},
        difficulty=sess.difficulty,
        userSide=sess.user_side,
        totalUserTurns=sess.total_user_turns,
        currentTurn=sess.current_turn,
        status=sess.status,
        turns=turn_schemas,
        skillReminder=sess.skill_reminder,
    )


@router.post("/{session_id}/turns", response_model=SubmitTurnResponseSchema)
async def submit_turn(
    session_id: str,
    audio: Optional[UploadFile] = File(None),
    transcript: Optional[str] = Form(None),
    audio_format: Optional[str] = Form("webm"),
    client_response_delay_ms: Optional[int] = Form(0),
    turn_index: Optional[int] = Form(None),
    idempotency_key: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts raw user audio bytes or text for the turn.
    Fans out MAI transcription and Modal phoneme processing concurrently.
    """
    sess_repo = DebateSessionRepository(db)
    session = await sess_repo.get_session(session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Debate session not found")

    if session.status == "finished":
        raise HTTPException(status_code=400, detail="Debate session is already finished")

    audio_bytes = None
    if audio:
        audio_bytes = await audio.read()

    fmt = audio_format or "webm"
    if audio and audio.filename and "." in audio.filename:
        fmt = audio.filename.rsplit(".", 1)[-1].lower()

    delay_ms = client_response_delay_ms or 0

    return await DebateOrchestrator.process_user_turn(
        db=db,
        session=session,
        user=user,
        audio_bytes=audio_bytes,
        transcript=transcript,
        audio_format=fmt,
        client_response_delay_ms=delay_ms,
        idempotency_key=idempotency_key,
    )


@router.get("/{session_id}/events")
async def observe_session_events(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Server-Sent Events (SSE) endpoint providing semantic lifecycle events:
    session.started, user.turn_submitted, opponent.thinking, opponent.turn_ready, review.ready.
    """
    sess_repo = DebateSessionRepository(db)
    session = await sess_repo.get_session(session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Debate session not found")

    queue = session_events.subscribe(session_id)

    async def event_generator():
        try:
            # Emit initial connect heartbeat
            yield f"data: {{\"type\": \"session.started\", \"data\": {{\"sessionId\": \"{session_id}\"}}}}\n\n"
            while True:
                data = await queue.get()
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            session_events.unsubscribe(session_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{session_id}/turns/{turn_id}/audio")
async def get_turn_audio(
    session_id: str,
    turn_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Plays ephemeral synthesized opponent audio.
    Regenerates on demand if cache expired.
    """
    audio_bytes = tts_cache.get(session_id, turn_id)
    if audio_bytes:
        return Response(content=audio_bytes, media_type="audio/mp3")

    # If missing from cache, check if opponent turn text exists in DB to re-synthesize
    sess_repo = DebateSessionRepository(db)
    session = await sess_repo.get_session(session_id)
    if session and session.user_id == user.id:
        turn = next((t for t in session.turns if t.id == turn_id), None)
        if turn and turn.speaker == "opponent" and turn.text_encrypted:
            txt = encryptor.decrypt_str(turn.text_encrypted)
            if txt:
                audio_bytes = await ai_gateway.synthesize_speech(txt)
                tts_cache.put(session_id, turn_id, audio_bytes)
                return Response(content=audio_bytes, media_type="audio/mp3")

    raise HTTPException(status_code=404, detail="Audio not found")


@router.post("/{session_id}/finish")
async def finish_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sess_repo = DebateSessionRepository(db)
    session = await sess_repo.get_session(session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Debate session not found")

    await DebateOrchestrator.finalize_debate_review(session_id, user.id)
    return {"status": "ok"}
