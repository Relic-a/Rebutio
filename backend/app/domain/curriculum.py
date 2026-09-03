from typing import Dict, List, Optional
from pydantic import BaseModel


class SkillDefinition(BaseModel):
    id: str
    order: int
    name: str
    description: str
    hint: str
    reminder: str
    spoken_focus: Optional[str] = None
    default_turns: int = 20
    default_minutes: int = 6
    default_difficulty: str = "steady"


CURRICULUM_SKILLS: List[SkillDefinition] = [
    SkillDefinition(
        id="take_a_side",
        order=1,
        name="Take a Side",
        description="State a clear position aloud and defend it with decisive spoken phrasing.",
        hint="Verbally declare your stance and hold it under pressure.",
        reminder="Pick a side, state it clearly in your first sentence, and commit to it.",
        spoken_focus="Direct stance declarations (e.g., 'I firmly contend that...', 'My position is unequivocal...')",
        default_turns=20,
        default_minutes=5,
        default_difficulty="gentle",
    ),
    SkillDefinition(
        id="give_a_reason",
        order=2,
        name="Give a Reason",
        description="Back your position aloud with a well-articulated reason and clear causal connectors.",
        hint="Give one clear spoken reason connecting your claim to an outcome.",
        reminder="State one clear reason aloud and explain the logical link.",
        spoken_focus="Causal transitions (e.g., 'This holds true because...', 'The primary driver is...')",
        default_turns=20,
        default_minutes=5,
        default_difficulty="gentle",
    ),
    SkillDefinition(
        id="back_it_up",
        order=3,
        name="Back It Up",
        description="Support your spoken reason with a concrete, vividly described example.",
        hint="Support your reason with a concrete spoken example.",
        reminder="Illustrate your reason with a specific, clearly narrated real-world example.",
        spoken_focus="Illustrative phrasing (e.g., 'To illustrate this in practice...', 'Consider the case where...')",
        default_turns=20,
        default_minutes=6,
        default_difficulty="gentle",
    ),
    SkillDefinition(
        id="counterpoint",
        order=4,
        name="Counterpoint",
        description="Build a spoken counter-argument that directly engages the opponent's claim.",
        hint="Make a direct spoken counterargument, not just a defense.",
        reminder="Don't just repeat your position. Respond directly to their strongest point with clear spoken contrast.",
        spoken_focus="Contrasting connectors (e.g., 'While the opposing claim suggests X, that overlooks Y...')",
        default_turns=20,
        default_minutes=6,
        default_difficulty="steady",
    ),
    SkillDefinition(
        id="counterargument",
        order=5,
        name="Counterargument",
        description="Deliver a structured counterargument with clear spoken refutation phrasing.",
        hint="Speak a direct counterargument challenging their underlying logic.",
        reminder="Deliver a direct counterargument that dismantles the opponent's premise aloud.",
        spoken_focus="Refutation signposts (e.g., 'That conclusion collapses when we examine...', 'The fatal flaw in that reasoning is...')",
        default_turns=20,
        default_minutes=6,
        default_difficulty="steady",
    ),
    SkillDefinition(
        id="rebuttal",
        order=6,
        name="Rebuttal",
        description="Respond directly to their strongest point with targeted, articulate spoken analysis.",
        hint="Respond directly to their strongest point with concise spoken reasoning.",
        reminder="Tackle their central argument head-on with clear, concise speech.",
        spoken_focus="Premise challenge collocations (e.g., 'Their premise relies on an unproven assumption...', 'Specifically, the evidence does not support...')",
        default_turns=20,
        default_minutes=7,
        default_difficulty="steady",
    ),
    SkillDefinition(
        id="concession",
        order=7,
        name="Concession",
        description="Concede part of their argument gracefully aloud without dropping your own thesis.",
        hint="Concede part of their argument aloud without dropping yours.",
        reminder="Concede part of their argument without abandoning your core spoken position.",
        spoken_focus="Concession and pivot language (e.g., 'While it is fair to concede that..., nonetheless...', 'Granted, X is valid; however...')",
        default_turns=20,
        default_minutes=8,
        default_difficulty="sharp",
    ),
    SkillDefinition(
        id="devils_advocate",
        order=8,
        name="Devil's Advocate",
        description="Defend an unfamiliar or unpopular position aloud with persuasive spoken conviction.",
        hint="Defend a counter-intuitive position aloud with authoritative vocabulary.",
        reminder="Defend the unpopular or contrary position aloud with spoken conviction and clear vocabulary.",
        spoken_focus="Perspective framing (e.g., 'From an alternative vantage point...', 'Proponents rightly emphasize...')",
        default_turns=20,
        default_minutes=7,
        default_difficulty="sharp",
    ),
    SkillDefinition(
        id="cross_examination",
        order=9,
        name="Cross Examination",
        description="Press their weakest point aloud with direct, incisive rhetorical questions.",
        hint="Press their weakest point aloud using direct spoken questions.",
        reminder="Press their weakest point aloud with targeted questioning and follow-up deduction.",
        spoken_focus="Rhetorical probing (e.g., 'How can that claim hold when...?', 'What mechanism accounts for...?')",
        default_turns=20,
        default_minutes=8,
        default_difficulty="sharp",
    ),
    SkillDefinition(
        id="evidence",
        order=10,
        name="Evidence",
        description="Weigh proof, data, and logical deduction aloud to substantiate your spoken claims.",
        hint="Support your spoken point with concrete evidence and logical deduction.",
        reminder="Ground your spoken point in verifiable evidence, analogies, and logical deduction.",
        spoken_focus="Evidentiary vocabulary (e.g., 'Empirical observations demonstrate that...', 'The causal link is established by...')",
        default_turns=20,
        default_minutes=8,
        default_difficulty="sharp",
    ),
    SkillDefinition(
        id="nuance",
        order=11,
        name="Nuance",
        description="Articulate competing principles and trade-offs aloud with balanced, sophisticated vocabulary.",
        hint="Weigh two competing principles aloud against each other.",
        reminder="Weigh competing principles against each other using measured, nuanced spoken phrasing.",
        spoken_focus="Trade-off and qualification phrasing (e.g., 'On balance, the critical distinction lies in...', 'This represents a trade-off between X and Y...')",
        default_turns=20,
        default_minutes=8,
        default_difficulty="sharp",
    ),
]

# Map includes curriculum skills plus benchmark workbench skills
SKILL_MAP: Dict[str, SkillDefinition] = {s.id: s for s in CURRICULUM_SKILLS}
SKILL_MAP["direct_refutation"] = SkillDefinition(
    id="direct_refutation",
    order=0,
    name="Direct Refutation",
    description="Target and dismantle the opponent's core premise aloud with sharp spoken refutation.",
    hint="Identify their key assumption aloud and refute it directly.",
    reminder="Directly challenge their central premise with clear spoken evidence and precise syntax.",
    spoken_focus="Premise-dismantling phrasing (e.g., 'Your claim assumes X, but in reality Y...', 'That premise overlooks...')",
    default_turns=3,
    default_minutes=6,
    default_difficulty="steady",
)


FIXTURE_TOPIC_TO_SKILL: Dict[str, str] = {
    "cats-dogs": "take_a_side",
    "money-happiness": "take_a_side",
    "uniforms": "give_a_reason",
    "video-games": "give_a_reason",
    "homework": "back_it_up",
    "social-media": "counterpoint",
    "ai-jobs": "counterargument",
    "ai-art": "counterargument",
    "college": "rebuttal",
    "algorithms": "rebuttal",
    "four-day": "rebuttal",
    "concession": "concession",
    "remote-work": "concession",
    "space-money": "concession",
    "identity-online": "devils_advocate",
    "phone-ban": "cross_examination",
    "free-speech": "evidence",
    "inequality": "nuance",
}

DEFAULT_SKILL_TOPICS: Dict[str, tuple[str, str]] = {
    "take_a_side": ("cats-dogs", "Cats are better pets than dogs."),
    "give_a_reason": ("uniforms", "School uniforms are actually a good idea."),
    "back_it_up": ("homework", "Homework should be abolished in primary school."),
    "counterpoint": ("social-media", "Social media has made friendships worse."),
    "counterargument": ("ai-jobs", "AI will create more jobs than it destroys."),
    "rebuttal": ("college", "College is no longer worth the cost."),
    "concession": ("remote-work", "Remote work is better for most careers than office work."),
    "devils_advocate": ("identity-online", "People should be allowed to use any name and identity online."),
    "cross_examination": ("phone-ban", "Schools should ban phones entirely during the day."),
    "evidence": ("free-speech", "Free speech should protect deliberately misleading speech."),
    "nuance": ("inequality", "Economic inequality is an unavoidable consequence of individual liberty."),
}


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
        # Never expose startable topicId for locked nodes
        node_topic_id = (topic_ids or {}).get(skill.id) if status != "locked" else None
        nodes.append({
            "id": skill.id,
            "order": skill.order,
            "name": skill.name,
            "description": skill.description,
            "stars": stars,
            "status": status,
            "topicId": node_topic_id,
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


def get_unlocked_skill_ids(stars_by_node: Dict[str, int]) -> set[str]:
    nodes = calculate_path_nodes(stars_by_node)
    return {n["id"] for n in nodes if n["status"] in ("current", "complete")}


def is_skill_unlocked(skill_id: str, stars_by_node: Dict[str, int]) -> bool:
    unlocked = get_unlocked_skill_ids(stars_by_node)
    return skill_id in unlocked


def get_skill_by_identifier(identifier: Optional[str]) -> Optional[SkillDefinition]:
    """
    Resolves a skill from:
    1. Direct skill ID (e.g. 'take_a_side', 'give_a_reason')
    2. Fixture topic ID (e.g. 'cats-dogs', 'uniforms', 'college')
    3. Numeric order / level (e.g. '1', '2', 1, 2)
    4. Prefixed order (e.g. 'level-1', 'level-2', 'debate-1', 'debate-2')
    """
    if not identifier:
        return None
    ident = str(identifier).strip().lower()
    if ident in SKILL_MAP:
        return SKILL_MAP[ident]
    if ident in FIXTURE_TOPIC_TO_SKILL:
        skill_id = FIXTURE_TOPIC_TO_SKILL[ident]
        return SKILL_MAP.get(skill_id)
    if ident.isdigit():
        order_num = int(ident)
        for s in CURRICULUM_SKILLS:
            if s.order == order_num:
                return s
    for prefix in ("level-", "level_", "debate-", "debate_", "step-", "step_"):
        if ident.startswith(prefix):
            suffix = ident[len(prefix):]
            if suffix.isdigit():
                order_num = int(suffix)
                for s in CURRICULUM_SKILLS:
                    if s.order == order_num:
                        return s
    return None
