from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user
from backend.app.domain.curriculum import CURRICULUM_SKILLS
from backend.app.models.db import User
from backend.app.models.schemas import (
    ProgressStatsSchema,
    SkillMasteryItemSchema,
)
from backend.app.persistence.db import get_db
from backend.app.persistence.repositories import (
    ProgressRepository,
    SpeechProfileRepository,
)

router = APIRouter(prefix="/api", tags=["progress"])


@router.get("/progress", response_model=ProgressStatsSchema)
async def get_progress(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    prog_repo = ProgressRepository(db)
    speech_repo = SpeechProfileRepository(db)

    prog = await prog_repo.get_progress(user.id)
    speech_prof = await speech_repo.get_profile(user.id) or {}

    stars_map = prog.stars_by_node_json or {}
    skill_mastery = []

    for skill in CURRICULUM_SKILLS[:4]:
        st = stars_map.get(skill.id, 0)
        level = "Strong" if st >= 2 else "Improving" if st == 1 else "Developing"
        skill_mastery.append(SkillMasteryItemSchema(skill=skill.name, level=level))

    pron_trend = None
    flu_trend = None

    rec_pron = speech_prof.get("recurring_pronunciation", [])
    if rec_pron:
        sound = rec_pron[0].get("sound", "th")
        pron_trend = f'"{sound}" sound pattern is showing consistent improvement.'
    else:
        pron_trend = 'Pronunciation clarity is consistent across arguments.'

    flu_summary = speech_prof.get("fluency_summary")
    if flu_summary:
        flu_trend = flu_summary
    else:
        flu_trend = "Response delays reflect strategic reasoning before speaking."

    return ProgressStatsSchema(
        xp=prog.xp,
        streakDays=prog.streak_days,
        streakHistory=prog.streak_history_json or [1, 1, 1, 0, 1, 1, 1],
        debatesCompleted=prog.debates_completed,
        wins=prog.wins,
        losses=prog.losses,
        draws=prog.draws,
        skillMastery=skill_mastery,
        pronunciationTrend=pron_trend,
        fluencyTrend=flu_trend,
    )
