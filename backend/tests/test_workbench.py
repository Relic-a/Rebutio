import pytest
from pathlib import Path

from workbench.modules.coach_mode import CoachModeEngine
from workbench.modules.debate_mode import DebateModeEngine
from workbench.modules.reviewer_mode import ReviewerEngine
from workbench.modules.topic_generator import TopicGeneratorEngine
from workbench.runner import WorkbenchRunner
from workbench.state.models import (
    CoachState,
    DebateState,
    ReviewState,
    TopicGeneratorInput,
    TopicGeneratorState,
)
from workbench.state.store import StateStore


@pytest.mark.asyncio
async def test_topic_generator_engine():
    inp = TopicGeneratorInput(skill_id="premise_clarity", count=2)
    state = TopicGeneratorState(inputs=inp)
    result = await TopicGeneratorEngine.run(state, live=False)

    assert len(result.generated_topics) == 2
    assert result.prompt_messages is not None
    assert len(result.prompt_messages) == 2
    assert result.duration_ms >= 0.0
    assert result.generated_topics[0].statement


@pytest.mark.asyncio
async def test_debate_mode_step_and_opponent():
    debate = StateStore.create_debate_from_topic(
        "Remote work should be legally protected.",
        user_side="agree",
        total_turns=3,
    )
    assert debate.current_turn == 1
    assert debate.status == "not_started"

    # User turn 1
    updated, opp_turn = await DebateModeEngine.step_turn(
        debate,
        user_text="Remote work saves commute time and improves worker well-being.",
        auto_opponent=True,
        live=False,
    )

    assert len(updated.turns) == 2
    assert updated.turns[0].speaker == "user"
    assert updated.turns[1].speaker == "opponent"
    assert updated.current_turn == 2
    assert updated.status == "active"
    assert opp_turn is not None
    assert len(opp_turn.text) > 20


@pytest.mark.asyncio
async def test_debate_mode_closing_statement_detection():
    debate = StateStore.create_debate_from_topic(
        "Remote work should be legally protected.",
        user_side="agree",
        total_turns=3,
    )
    # Closing statement in turn 1
    updated, opp_turn = await DebateModeEngine.step_turn(
        debate,
        user_text="In conclusion, this policy is essential for all workers. That concludes my case.",
        auto_opponent=True,
        live=False,
    )

    assert updated.status == "finished"
    assert updated.is_closing_statement is True
    assert "Closing phrase detected" in (updated.closing_reason or "")
    assert opp_turn is None  # Opponent should not speak after closing


@pytest.mark.asyncio
async def test_reviewer_engine_strong_debate():
    debate = StateStore.load_state(DebateState, "debates/completed_strong.json")
    review = await ReviewerEngine.run_review(debate, live=False)

    assert review.evidence_assessment.has_sufficient_evidence is True
    assert review.evidence_assessment.has_sufficient_delivery_evidence is True
    assert review.outcome == "user_win"
    assert review.mastery_stars == 3
    assert review.score_technique.score == 9
    assert review.score_grammar.score == 9
    assert review.score_vocabulary.score == 8
    assert review.score_delivery.score == 8
    assert review.language_feedback is not None
    assert len(review.language_feedback["pronunciation"]) > 0


@pytest.mark.asyncio
async def test_reviewer_engine_insufficient_evidence():
    debate = StateStore.load_state(DebateState, "debates/completed_insufficient.json")
    review = await ReviewerEngine.run_review(debate, live=False)

    assert review.evidence_assessment.has_sufficient_evidence is False
    assert review.outcome == "undetermined"
    assert review.mastery_stars == 0
    assert review.score_technique.score is None
    assert "Insufficient debate exchanges" in review.score_technique.rubric


@pytest.mark.asyncio
async def test_coach_mode_opening_analysis():
    coach_state = StateStore.load_state(CoachState, "coach/ready_for_opening.json")
    updated_state, opening = await CoachModeEngine.generate_opening_analysis(coach_state, live=False)

    assert opening.overall_assessment
    assert opening.most_important_strength
    assert opening.highest_value_improvement
    assert len(opening.suggested_quick_replies) > 0
    assert len(updated_state.thread_messages) == 1
    assert updated_state.thread_messages[0].message_type == "opening_analysis"


@pytest.mark.asyncio
async def test_coach_mode_chat_and_tools():
    coach_state = StateStore.load_state(CoachState, "coach/ready_for_opening.json")
    updated_state, msg = await CoachModeEngine.process_coach_turn(
        coach_state,
        user_message="Give me a 1-minute drill for pronunciation.",
        live=False,
    )

    assert msg.sender == "coach"
    assert len(msg.text) > 20
    assert len(updated_state.thread_messages) == 2  # user + coach
    assert updated_state.thread_messages[0].sender == "user"
    assert updated_state.thread_messages[1].sender == "coach"


@pytest.mark.asyncio
async def test_coach_mode_memory_update():
    coach_state = StateStore.load_state(CoachState, "coach/ready_for_opening.json")
    updated_state, new_md, diff = await CoachModeEngine.update_coach_memory(coach_state, live=False)

    assert diff["lines_added"] > 0
    assert "### [" in new_md
    assert "Debate:" in new_md
    assert updated_state.coach_memory_markdown == new_md


@pytest.mark.asyncio
async def test_state_store_save_and_load_roundtrip(tmp_path):
    debate = StateStore.create_debate_from_topic("Test topic statement", user_side="agree")
    saved_path = StateStore.save_state(debate, filename="test_roundtrip")

    loaded = StateStore.load_state(DebateState, saved_path)
    assert loaded.topic == debate.topic
    assert loaded.session_id == debate.session_id
    assert loaded.user_side == "agree"

    # Clean up test file
    if saved_path.exists():
        saved_path.unlink()


@pytest.mark.asyncio
async def test_full_pipeline_run():
    pipeline_result = await WorkbenchRunner.run_full_pipeline(
        skill_id="direct_refutation",
        difficulty="steady",
        live=False,
        save=False,
    )

    assert pipeline_result["topic_state"].generated_topics
    assert pipeline_result["debate_state"].status == "finished"
    assert pipeline_result["review_state"].completed is True
    assert pipeline_result["coach_state"].opening_analysis is not None
    assert pipeline_result["summary"]["outcome"] in ("user_win", "draw")
    assert pipeline_result["total_duration_ms"] > 0.0
