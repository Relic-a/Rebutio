from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user
from backend.app.domain.curriculum import calculate_path_nodes
from backend.app.models.db import User
from backend.app.models.schemas import (
    BootstrapInfoSchema,
    DebateSessionSchema,
    DebateTurnPlaybackSchema,
    DebateTurnSchema,
    LearningPathSchema,
    OnboardingPreferencesSchema,
    SkillTargetSchema,
)
from backend.app.persistence.db import get_db
from backend.app.persistence.repositories import (
    DebateSessionRepository,
    ProgressRepository,
    UserRepository,
)
from backend.app.services.privacy.encryption import encryptor

router = APIRouter(prefix="/api", tags=["bootstrap"])


@router.get("/bootstrap", response_model=BootstrapInfoSchema)
async def get_app_bootstrap(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_repo = UserRepository(db)
    prog_repo = ProgressRepository(db)
    sess_repo = DebateSessionRepository(db)

    prog = await prog_repo.get_progress(user.id)
    stars_by_node = prog.stars_by_node_json or {}
    nodes = calculate_path_nodes(stars_by_node)

    # Determine current level index and name
    current_node = next((n for n in nodes if n["status"] == "current"), nodes[0])
    level_num = current_node["order"]
    level_name = current_node["name"]

    prefs_dict = user_repo.get_preferences(user)
    prefs_schema = OnboardingPreferencesSchema(**prefs_dict) if prefs_dict else None

    # Check for active resumable debate session
    active_session_db = await sess_repo.get_active_session_for_user(user.id)
    active_session_schema = None
    if active_session_db:
        turns_schemas = []
        for t in active_session_db.turns:
            txt = encryptor.decrypt_str(t.text_encrypted) if t.text_encrypted else None
            audio_url = f"/api/sessions/{active_session_db.id}/turns/{t.id}/audio" if t.audio_available else None
            turns_schemas.append(
                DebateTurnSchema(
                    id=t.id,
                    speaker=t.speaker,
                    text=txt,
                    playback=DebateTurnPlaybackSchema(
                        available=t.audio_available,
                        audioUrl=audio_url,
                        durationSec=t.duration_sec,
                    ),
                    durationSec=t.duration_sec,
                    move=t.move,
                    requiresResponse=t.requires_response,
                    addressedClaim=t.addressed_claim,
                    conversationState=t.conversation_state,
                    mediaAssetId=t.media_asset_id,
                )
            )
        active_session_schema = DebateSessionSchema(
            id=active_session_db.id,
            topic=active_session_db.topic_text,
            skillTarget=SkillTargetSchema(
                id=active_session_db.skill_id,
                name=active_session_db.skill_name,
                hint=active_session_db.skill_hint,
            ),
            difficulty=active_session_db.difficulty,
            userSide=active_session_db.user_side,
            totalUserTurns=active_session_db.total_user_turns,
            currentTurn=active_session_db.current_turn,
            status=active_session_db.status,
            turns=turns_schemas,
            skillReminder=active_session_db.skill_reminder,
            isOnboarding=active_session_db.is_onboarding,
        )

    return BootstrapInfoSchema(
        onboarded=user.onboarded,
        path=LearningPathSchema(
            levelName=level_name,
            levelNumber=level_num,
            nodes=nodes,
        ),
        preferences=prefs_schema,
        saveTranscripts=user.save_transcripts,
        captionsEnabled=user.captions_enabled,
        activeSession=active_session_schema,
    )
