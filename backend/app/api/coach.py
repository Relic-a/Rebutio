from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user
from backend.app.domain.orchestration import DebateOrchestrator
from backend.app.models.db import User
from backend.app.models.schemas import (
    CoachHomeSchema,
    CoachMessageSchema,
    CoachThreadDetailSchema,
    CoachThreadSummarySchema,
    DebateSessionSchema,
    MemoryCorrectionRequestSchema,
    SendTextMessageRequestSchema,
)
from backend.app.observability.logging import get_logger
from backend.app.persistence.db import get_db
from backend.app.persistence.repositories import (
    CoachRepository,
    DebateSessionRepository,
    UserRepository,
)
from backend.app.services.ai.gateway import ai_gateway
from backend.app.services.coach.engine import CoachEngine, coach_engine
from backend.app.services.privacy.encryption import encryptor

logger = get_logger("rebutio.api.coach")
router = APIRouter(prefix="/api/coach", tags=["coach"])


@router.get("/home", response_model=CoachHomeSchema)
async def get_coach_home(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns data for the Coach Home page:
    Active focus, longitudinal trends, quick questions, recent debate threads, general threads.
    """
    user_repo = UserRepository(db)
    await user_repo.get_or_create_user(user.id)
    return await CoachEngine.get_coach_home_data(db, user.id)


@router.get("/session/{session_id}", response_model=CoachThreadDetailSchema)
async def get_or_create_session_coach_thread(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns or creates the session-specific Coach thread for a completed debate.
    Generates proactive opening analysis if thread is newly created.
    """
    try:
        thread = await CoachEngine.get_or_create_debate_coach_thread(db, user.id, session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    coach_repo = CoachRepository(db)
    sess_repo = DebateSessionRepository(db)
    session = await sess_repo.get_session(thread.session_id) if thread.session_id else None
    review = await sess_repo.get_review(thread.session_id) if thread.session_id else None

    topic = session.topic_text if session else "Debate Review"
    skill = session.skill_name if session else "Refutation"

    debate_session_schema = None
    if session:
        turns = []
        for t in (session.turns or []):
            txt = encryptor.decrypt_str(t.text_encrypted) if t.text_encrypted else ""
            turns.append({
                "id": t.id,
                "speaker": t.speaker,
                "text": txt,
                "playback": {"available": t.audio_available},
                "move": t.move,
                "requiresResponse": t.requires_response,
                "addressedClaim": t.addressed_claim,
                "conversationState": t.conversation_state,
                "mediaAssetId": t.media_asset_id,
            })
        debate_session_schema = DebateSessionSchema(
            id=session.id,
            topic=session.topic_text,
            skillTarget={"id": session.skill_id or "direct_rebuttal", "name": session.skill_name or "Direct Rebuttal", "hint": session.skill_reminder or ""},
            difficulty=session.difficulty or "steady",
            userSide=session.user_side or "agree",
            totalUserTurns=session.total_user_turns or 3,
            currentTurn=session.current_turn or 1,
            status=session.status or "finished",
            turns=turns,
            skillReminder=session.skill_reminder or "",
        )

    debate_review_schema = None
    if review and session:
        debate_review_schema = DebateOrchestrator._db_review_to_schema(
            review, session.id, session.topic_text, session.skill_name
        )

    messages = await coach_repo.get_thread_messages(thread.id)
    msg_schemas = [CoachEngine._message_to_schema(m) for m in messages]

    summary = CoachThreadSummarySchema(
        id=thread.id,
        sessionId=thread.session_id,
        threadType=thread.thread_type,
        title=thread.title,
        createdAt=thread.created_at.isoformat() if thread.created_at else "",
        updatedAt=thread.updated_at.isoformat() if thread.updated_at else "",
        messageCount=len(messages),
        topic=topic,
        skillName=skill,
    )

    return CoachThreadDetailSchema(
        thread=summary,
        messages=msg_schemas,
        debateSession=debate_session_schema,
        debateReview=debate_review_schema,
    )


@router.post("/threads", response_model=CoachThreadDetailSchema)
async def create_general_coach_thread(
    req: SendTextMessageRequestSchema,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Creates a new general coaching thread and processes the opening prompt.
    """
    coach_repo = CoachRepository(db)
    title = req.text[:40] if req.text else "General Coaching"
    thread = await coach_repo.create_general_thread(user_id=user.id, title=title)

    # Process first message
    await CoachEngine.process_user_text_message(
        db=db,
        user_id=user.id,
        thread_id=thread.id,
        text=req.text,
    )

    messages = await coach_repo.get_thread_messages(thread.id)
    msg_schemas = [CoachEngine._message_to_schema(m) for m in messages]

    summary = CoachThreadSummarySchema(
        id=thread.id,
        sessionId=None,
        threadType="general",
        title=thread.title,
        createdAt=thread.created_at.isoformat() if thread.created_at else "",
        updatedAt=thread.updated_at.isoformat() if thread.updated_at else "",
        messageCount=len(messages),
    )

    return CoachThreadDetailSchema(
        thread=summary,
        messages=msg_schemas,
    )


@router.get("/threads/{thread_id}", response_model=CoachThreadDetailSchema)
async def get_coach_thread_detail(
    thread_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    coach_repo = CoachRepository(db)
    thread = await coach_repo.get_thread(user.id, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    topic = thread.session.topic_text if thread.session else None
    skill = thread.session.skill_name if thread.session else None

    messages = await coach_repo.get_thread_messages(thread.id)
    msg_schemas = [CoachEngine._message_to_schema(m) for m in messages]

    summary = CoachThreadSummarySchema(
        id=thread.id,
        sessionId=thread.session_id,
        threadType=thread.thread_type,
        title=thread.title,
        createdAt=thread.created_at.isoformat() if thread.created_at else "",
        updatedAt=thread.updated_at.isoformat() if thread.updated_at else "",
        messageCount=len(messages),
        topic=topic,
        skillName=skill,
    )

    return CoachThreadDetailSchema(
        thread=summary,
        messages=msg_schemas,
    )


@router.post("/threads/{thread_id}/messages", response_model=CoachMessageSchema)
async def send_coach_text_message(
    thread_id: str,
    req: SendTextMessageRequestSchema,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Sends a text message to the coach in an existing thread and returns the coach response.
    """
    if not req.text.strip():
        raise HTTPException(status_code=422, detail="Message text cannot be empty")

    try:
        reply_msg = await CoachEngine.process_user_text_message(
            db=db,
            user_id=user.id,
            thread_id=thread_id,
            text=req.text.strip(),
        )
        return reply_msg
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("coach.text_message_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to process coach message")


@router.post("/threads/{thread_id}/audio")
async def send_coach_audio_message(
    thread_id: str,
    audio: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Uploads a spoken practice / question audio message to the coach.
    Transcribes, extracts phonemes, saves media asset, and generates evidence-based coach reply.
    """
    audio_bytes = await audio.read()
    if len(audio_bytes) < 100:
        raise HTTPException(status_code=422, detail="Audio file too short or empty")

    mime_type = audio.content_type or "audio/webm"
    try:
        user_msg, coach_msg = await CoachEngine.process_user_audio_message(
            db=db,
            user_id=user.id,
            thread_id=thread_id,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
        )
        return {
            "userMessage": user_msg.model_dump(),
            "coachMessage": coach_msg.model_dump(),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("coach.audio_message_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to process audio message")


@router.get("/pronunciation")
async def get_pronunciation_audio(
    text: str,
    user: User = Depends(get_current_user),
):
    """Return a short professional TTS pronunciation for an inline coach tag."""
    pronunciation_text = " ".join(text.strip().split())
    if not pronunciation_text or len(pronunciation_text) > 60:
        raise HTTPException(status_code=422, detail="Pronunciation text must be between 1 and 60 characters")

    audio_bytes = await ai_gateway.synthesize_speech(pronunciation_text)
    if not audio_bytes:
        raise HTTPException(status_code=503, detail="Pronunciation audio is temporarily unavailable")

    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.post("/memory/correction")
async def correct_coaching_memory(
    req: MemoryCorrectionRequestSchema,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Allows the user to correct, update, or add a coaching preference note to their canonical memory document.
    """
    coach_repo = CoachRepository(db)
    updated_md = await coach_repo.apply_user_memory_correction(
        user_id=user.id,
        correction_text=req.correctionText,
        action=req.action or "update",
        label=req.label,
    )
    return {
        "success": True,
        "memoryMarkdown": updated_md,
    }

