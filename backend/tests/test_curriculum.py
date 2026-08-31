import pytest
from backend.app.domain.curriculum import (
    CURRICULUM_SKILLS,
    calculate_path_nodes,
    get_current_skill_for_user,
    get_skill,
)


def test_curriculum_skills_count_and_order():
    assert len(CURRICULUM_SKILLS) == 11
    assert CURRICULUM_SKILLS[0].id == "take_a_side"
    assert CURRICULUM_SKILLS[0].order == 1
    assert CURRICULUM_SKILLS[1].id == "give_a_reason"
    assert CURRICULUM_SKILLS[1].order == 2


def test_calculate_path_nodes_fresh_user():
    nodes = calculate_path_nodes({})
    assert len(nodes) == 11
    assert nodes[0]["status"] == "current"
    assert nodes[0]["stars"] == 0
    assert nodes[1]["status"] == "locked"
    assert nodes[2]["status"] == "locked"


def test_calculate_path_nodes_progression_one_star_rule():
    # 1 star on take_a_side unlocks give_a_reason
    nodes = calculate_path_nodes({"take_a_side": 1})
    assert nodes[0]["status"] == "complete"
    assert nodes[0]["stars"] == 1
    assert nodes[1]["status"] == "current"
    assert nodes[1]["stars"] == 0
    assert nodes[2]["status"] == "locked"

    # 2 stars on give_a_reason unlocks back_it_up
    nodes2 = calculate_path_nodes({"take_a_side": 1, "give_a_reason": 2})
    assert nodes2[0]["status"] == "complete"
    assert nodes2[1]["status"] == "complete"
    assert nodes2[2]["status"] == "current"
    assert nodes2[3]["status"] == "locked"


def test_calculate_path_nodes_keeps_topic_id_with_preview():
    nodes = calculate_path_nodes(
        {},
        topic_previews={"take_a_side": "Cats are better pets than dogs."},
        topic_ids={"take_a_side": "cats-dogs"},
    )

    assert nodes[0]["topicId"] == "cats-dogs"
    assert nodes[0]["topicPreview"] == "Cats are better pets than dogs."
