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
from backend.app.observability.context import bind_context
from backend.app.observability.logging import get_logger
from backend.app.persistence.db import get_db
from backend.app.persistence.repositories import DebateSessionRepository
from backend.app.services.ai.gateway import ai_gateway
from backend.app.services.privacy.encryption import encryptor
from backend.app.services.tts.cache import tts_cache

logger = get_logger("rebutio.sessions")
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
    bind_context(session_id=session_id, user_id=user.id)
    sess_repo = DebateSessionRepository(db)
    sess = await sess_repo.get_session(session_id)
    if not sess or sess.user_id != user.id:
        raise HTTPException(status_code=404, detail="Debate session not found")

    turns = await sess_repo.get_turns(session_id)
    turn_schemas = []
    for t in turns:
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
    bind_context(session_id=session_id, user_id=user.id, turn_id=turn_index)
    sess_repo = DebateSessionRepository(db)
    session = await sess_repo.get_session(session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Debate session not found")

    if session.status != "active":
        raise HTTPException(
            status_code=400,
            detail=f"Debate session is not active (current status: '{session.status}')",
        )

    ALLOWED_FORMATS = {"webm", "wav", "mp4", "m4a", "ogg", "mp3", "aac"}
    MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25MB limit

    audio_bytes = None
    if audio:
        audio_bytes = await audio.read()
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            logger.warning("audio.upload_rejected", reason="exceeds_25mb_limit", size_bytes=len(audio_bytes))
            raise HTTPException(status_code=400, detail="Audio file exceeds 25MB limit")

    fmt = (audio_format or "webm").lower().strip(".")
    if audio and audio.filename and "." in audio.filename:
        ext = audio.filename.rsplit(".", 1)[-1].lower()
        if ext in ALLOWED_FORMATS:
            fmt = ext

    if fmt not in ALLOWED_FORMATS:
        fmt = "webm"

    # Idempotency check: if turn_index is less than current turn, return already saved turn
    if turn_index is not None and turn_index < session.current_turn:
        logger.info(
            "debate.turn.retry_detected",
            session_id=session_id,
            requested_turn=turn_index,
            current_turn=session.current_turn,
        )
        saved_turns = await sess_repo.get_turns(session_id)
        user_t = next((t for t in saved_turns if t.turn_number == turn_index and t.speaker == "user"), None)
        opp_t = next((t for t in saved_turns if t.turn_number == turn_index and t.speaker == "opponent"), None)
        if user_t:
            u_txt = encryptor.decrypt_str(user_t.text_encrypted) if user_t.text_encrypted else None
            o_txt = encryptor.decrypt_str(opp_t.text_encrypted) if opp_t and opp_t.text_encrypted else None
            o_audio = f"/api/sessions/{session_id}/turns/{opp_t.id}/audio" if opp_t else None
            return SubmitTurnResponseSchema(
                userTurn=DebateTurnSchema(id=user_t.id, speaker="user", text=u_txt, playback={"available": user_t.audio_available}),
                opponentTurn=DebateTurnSchema(id=opp_t.id, speaker="opponent", text=o_txt, playback={"available": True, "audioUrl": o_audio}) if opp_t else None,
                nextUserTurnNumber=session.current_turn,
                finished=(session.status == "finished"),
            )

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
    bind_context(session_id=session_id, user_id=user.id)
    sess_repo = DebateSessionRepository(db)
    session = await sess_repo.get_session(session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Debate session not found")

    logger.debug("event_stream.connected", session_id=session_id)
    queue = session_events.subscribe(session_id)

    async def event_generator():
        try:
            # Emit initial connect heartbeat
            yield f"data: {{\"type\": \"session.started\", \"data\": {{\"sessionId\": \"{session_id}\"}}}}\n\n"
            while True:
                data = await queue.get()
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            logger.debug("event_stream.disconnected", session_id=session_id)
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
    bind_context(session_id=session_id, user_id=user.id, turn_id=turn_id)
    audio_bytes = tts_cache.get(session_id, turn_id)
    if audio_bytes:
        logger.debug("debate.tts.cache_hit", session_id=session_id, turn_id=turn_id)
        media_type = "audio/wav" if audio_bytes.startswith(b"RIFF") else "audio/mpeg"
        return Response(content=audio_bytes, media_type=media_type)

    logger.info("debate.tts.cache_miss_regenerating", session_id=session_id, turn_id=turn_id)
    # If missing from cache, check if opponent turn text exists in DB to re-synthesize
    sess_repo = DebateSessionRepository(db)
    session = await sess_repo.get_session(session_id)
    if session and session.user_id == user.id:
        turns = await sess_repo.get_turns(session_id)
        turn = next((t for t in turns if t.id == turn_id), None)
        if turn and turn.speaker == "opponent" and turn.text_encrypted:
            txt = encryptor.decrypt_str(turn.text_encrypted)
            if txt:
                audio_bytes = await ai_gateway.synthesize_speech(txt)
                if audio_bytes:
                    tts_cache.put(session_id, turn_id, audio_bytes)
                    media_type = "audio/wav" if audio_bytes.startswith(b"RIFF") else "audio/mpeg"
                    return Response(content=audio_bytes, media_type=media_type)

    raise HTTPException(status_code=404, detail="Audio not found")


@router.post("/{session_id}/finish")
async def finish_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    bind_context(session_id=session_id, user_id=user.id)
    sess_repo = DebateSessionRepository(db)
    session = await sess_repo.get_session(session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Debate session not found")

    # Mark session as finished/review_pending in DB immediately so bootstrap / session state
    # never presents a stale 'active' status while review is being processed.
    session.status = "finished"
    await db.commit()

    logger.info("session.manual_finish_triggered", session_id=session_id, user_id=user.id)
    await DebateOrchestrator.finalize_debate_review(session_id, user.id)
    return {"status": "ok"}
