from typing import Dict, List, Optional
from pydantic import BaseModel


class SkillDefinition(BaseModel):
    id: str
    order: int
    name: str
    description: str
    hint: str
    reminder: str
    default_turns: int = 4
    default_minutes: int = 6
    default_difficulty: str = "steady"


CURRICULUM_SKILLS: List[SkillDefinition] = [
    SkillDefinition(
        id="take_a_side",
        order=1,
        name="Take a Side",
        description="State a position and hold it under pressure.",
        hint="Pick a side and hold it.",
        reminder="Pick a side and commit to it.",
        default_turns=3,
        default_minutes=5,
        default_difficulty="gentle",
    ),
    SkillDefinition(
        id="give_a_reason",
        order=2,
        name="Give a Reason",
        description="Back your position with a clear reason.",
        hint="Give one clear reason for your side.",
        reminder="Give one clear reason and defend it.",
        default_turns=3,
        default_minutes=5,
        default_difficulty="gentle",
    ),
    SkillDefinition(
        id="back_it_up",
        order=3,
        name="Back It Up",
        description="Support your reason with a concrete example.",
        hint="Support your reason with a concrete example.",
        reminder="Support your reason with a concrete example.",
        default_turns=4,
        default_minutes=6,
        default_difficulty="gentle",
    ),
    SkillDefinition(
        id="counterpoint",
        order=4,
        name="Counterpoint",
        description="Build an argument against theirs, not just for yours.",
        hint="Make a counterargument, not just a defense.",
        reminder="Don't just repeat your position. Respond directly to their strongest point.",
        default_turns=4,
        default_minutes=6,
        default_difficulty="steady",
    ),
    SkillDefinition(
        id="counterargument",
        order=5,
        name="Counterargument",
        description="Make a counterargument, not just a defense.",
        hint="Make a counterargument, not just a defense.",
        reminder="Make a counterargument, not just a defense.",
        default_turns=4,
        default_minutes=6,
        default_difficulty="steady",
    ),
    SkillDefinition(
        id="rebuttal",
        order=6,
        name="Rebuttal",
        description="Respond directly to their strongest point.",
        hint="Respond directly to their strongest point.",
        reminder="Respond directly to their strongest point.",
        default_turns=4,
        default_minutes=7,
        default_difficulty="steady",
    ),
    SkillDefinition(
        id="concession",
        order=7,
        name="Concession",
        description="Concede part of their argument without dropping yours.",
        hint="Concede part of their argument without dropping yours.",
        reminder="Concede part of their argument without abandoning your position.",
        default_turns=5,
        default_minutes=8,
        default_difficulty="sharp",
    ),
    SkillDefinition(
        id="devils_advocate",
        order=8,
        name="Devil's Advocate",
        description="Defend a position you don't personally agree with.",
        hint="Defend a position you don't personally agree with.",
        reminder="Defend the unpopular or contrary position with conviction.",
        default_turns=4,
        default_minutes=7,
        default_difficulty="sharp",
    ),
    SkillDefinition(
        id="cross_examination",
        order=9,
        name="Cross Examination",
        description="Press their weakest point with direct questions.",
        hint="Press their weakest point with a direct question.",
        reminder="Press their weakest point with a direct question.",
        default_turns=5,
        default_minutes=8,
        default_difficulty="sharp",
    ),
    SkillDefinition(
        id="evidence",
        order=10,
        name="Evidence",
        description="Weigh examples and proof, not just opinions.",
        hint="Support your point with a concrete example.",
        reminder="Support your point with concrete evidence and logical deduction.",
        default_turns=5,
        default_minutes=8,
        default_difficulty="sharp",
    ),
    SkillDefinition(
        id="nuance",
        order=11,
        name="Nuance",
        description="Compare competing principles in abstract debate.",
        hint="Weigh two competing principles against each other.",
        reminder="Weigh two competing principles against each other.",
        default_turns=5,
        default_minutes=8,
        default_difficulty="sharp",
    ),
]

SKILL_MAP: Dict[str, SkillDefinition] = {s.id: s for s in CURRICULUM_SKILLS}


def get_skill(skill_id: str) -> SkillDefinition:
    return SKILL_MAP.get(skill_id, CURRICULUM_SKILLS[0])


def calculate_path_nodes(
    stars_by_node: Dict[str, int],
    topic_previews: Optional[Dict[str, str]] = None,
    topic_ids: Optional[Dict[str, str]] = None,
) -> List[dict]:
    """
    Computes node statuses ('complete', 'current', 'locked') and star counts.
    Rule: A node unlocks when the previous node has >= 1 star.
    First node is always unlocked.
    """
    nodes = []
    prev_completed = True  # first node is unlocked by default
    current_found = False

    for skill in CURRICULUM_SKILLS:
        stars = max(0, min(3, stars_by_node.get(skill.id, 0)))
        status = "locked"

        if stars >= 1:
            status = "complete"
            prev_completed = True
        elif prev_completed and not current_found:
            status = "current"
            current_found = True
            prev_completed = False
        else:
            status = "locked"
            prev_completed = False

        preview = (topic_previews or {}).get(skill.id)
        nodes.append({
            "id": skill.id,
            "order": skill.order,
            "name": skill.name,
            "description": skill.description,
            "stars": stars,
            "status": status,
            "topicId": (topic_ids or {}).get(skill.id),
            "topicPreview": preview,
        })

    # If no node was marked 'current' (e.g. none completed yet), the first node is 'current'
    if not current_found and nodes and nodes[0]["status"] != "complete":
        nodes[0]["status"] = "current"

    return nodes


def get_current_skill_for_user(stars_by_node: Dict[str, int]) -> SkillDefinition:
    nodes = calculate_path_nodes(stars_by_node)
    for n in nodes:
        if n["status"] == "current":
            return get_skill(n["id"])
    return CURRICULUM_SKILLS[0]
