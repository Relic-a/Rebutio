from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user
from backend.app.domain.curriculum import calculate_path_nodes
from backend.app.models.db import User
from backend.app.models.schemas import (
    BootstrapInfoSchema,
    LearningPathSchema,
    OnboardingPreferencesSchema,
)
from backend.app.persistence.db import get_db
from backend.app.persistence.repositories import (
    ProgressRepository,
    UserRepository,
)

router = APIRouter(prefix="/api", tags=["bootstrap"])


@router.get("/bootstrap", response_model=BootstrapInfoSchema)
async def get_app_bootstrap(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_repo = UserRepository(db)
    prog_repo = ProgressRepository(db)

    prog = await prog_repo.get_progress(user.id)
    stars_by_node = prog.stars_by_node_json or {}
    nodes = calculate_path_nodes(stars_by_node)

    # Determine current level index and name
    current_node = next((n for n in nodes if n["status"] == "current"), nodes[0])
    level_num = current_node["order"]
    level_name = current_node["name"]

    prefs_dict = user_repo.get_preferences(user)
    prefs_schema = OnboardingPreferencesSchema(**prefs_dict) if prefs_dict else None

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
    )
