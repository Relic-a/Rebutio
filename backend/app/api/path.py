from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user
from backend.app.domain.curriculum import calculate_path_nodes
from backend.app.models.db import User
from backend.app.models.schemas import LearningPathSchema
from backend.app.persistence.db import get_db
from backend.app.persistence.repositories import (
    ProgressRepository,
    TopicInventoryRepository,
)

router = APIRouter(prefix="/api", tags=["path"])


@router.get("/path", response_model=LearningPathSchema)
async def get_learning_path(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    prog_repo = ProgressRepository(db)
    topic_repo = TopicInventoryRepository(db)

    prog = await prog_repo.get_progress(user.id)
    stars_map = prog.stars_by_node_json or {}

    available_topics = await topic_repo.get_available_topics(user.id, limit=20)
    topic_previews = {t.skill_id: t.topic_text for t in available_topics}

    nodes = calculate_path_nodes(stars_map, topic_previews=topic_previews)
    current_node = next((n for n in nodes if n["status"] == "current"), nodes[0])

    return LearningPathSchema(
        levelName=current_node["name"],
        levelNumber=current_node["order"],
        nodes=nodes,
    )
