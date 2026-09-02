from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

from workbench.modules.coach_mode import CoachModeEngine
from workbench.modules.debate_mode import DebateModeEngine
from workbench.modules.reviewer_mode import ReviewerEngine
from workbench.modules.topic_generator import TopicGeneratorEngine
from workbench.state.models import (
    CoachMessageItem,
    CoachOpeningAnalysis,
    CoachState,
    DebateState,
    DebateTurn,
    GeneratedTopic,
    ReviewState,
    TopicGeneratorInput,
    TopicGeneratorState,
)
from workbench.state.store import StateStore


class WorkbenchRunner:
    """
    Unified execution API for isolated modules and end-to-end pipeline runs.
    """

    @classmethod
    async def run_topic_generation(
        cls,
        state_or_input: Optional[Union[TopicGeneratorState, TopicGeneratorInput, str, Path]] = None,
        live: bool = False,
        save: bool = False,
    ) -> TopicGeneratorState:
        if isinstance(state_or_input, (str, Path)):
            state = StateStore.load_state(TopicGeneratorState, state_or_input)
        elif isinstance(state_or_input, TopicGeneratorInput):
            state = TopicGeneratorState(inputs=state_or_input)
        elif isinstance(state_or_input, TopicGeneratorState):
            state = state_or_input
        else:
            state = TopicGeneratorState()

        result = await TopicGeneratorEngine.run(state, live=live)
        if save:
            StateStore.save_state(result)
        return result

    @classmethod
    async def run_debate_step(
        cls,
        debate_or_path: Union[DebateState, str, Path],
        user_text: str,
        audio_metrics: Optional[Dict[str, Any]] = None,
        auto_opponent: bool = True,
        live: bool = False,
        save: bool = False,
    ) -> Tuple[DebateState, Optional[DebateTurn]]:
        if isinstance(debate_or_path, (str, Path)):
            state = StateStore.load_state(DebateState, debate_or_path)
        else:
            state = debate_or_path

        updated_state, opponent_turn = await DebateModeEngine.step_turn(
            state=state,
            user_text=user_text,
            audio_metrics=audio_metrics,
            auto_opponent=auto_opponent,
            live=live,
        )
        if save:
            StateStore.save_state(updated_state)
        return updated_state, opponent_turn

    @classmethod
    async def run_review(
        cls,
        debate_or_path: Union[DebateState, str, Path],
        live: bool = False,
        save: bool = False,
    ) -> ReviewState:
        if isinstance(debate_or_path, (str, Path)):
            debate_state = StateStore.load_state(DebateState, debate_or_path)
        else:
            debate_state = debate_or_path

        review_state = await ReviewerEngine.run_review(debate_state, live=live)
        if save:
            StateStore.save_state(review_state)
        return review_state

    @classmethod
    async def run_coach_opening(
        cls,
        coach_or_path: Union[CoachState, str, Path],
        live: bool = False,
        save: bool = False,
    ) -> Tuple[CoachState, CoachOpeningAnalysis]:
        if isinstance(coach_or_path, (str, Path)):
            coach_state = StateStore.load_state(CoachState, coach_or_path)
        else:
            coach_state = coach_or_path

        updated_state, analysis = await CoachModeEngine.generate_opening_analysis(coach_state, live=live)
        if save:
            StateStore.save_state(updated_state)
        return updated_state, analysis

    @classmethod
    async def run_coach_chat(
        cls,
        coach_or_path: Union[CoachState, str, Path],
        user_message: str,
        live: bool = False,
        save: bool = False,
    ) -> Tuple[CoachState, CoachMessageItem]:
        if isinstance(coach_or_path, (str, Path)):
            coach_state = StateStore.load_state(CoachState, coach_or_path)
        else:
            coach_state = coach_or_path

        updated_state, coach_msg = await CoachModeEngine.process_coach_turn(coach_state, user_message=user_message, live=live)
        if save:
            StateStore.save_state(updated_state)
        return updated_state, coach_msg

    @classmethod
    async def run_coach_memory_update(
        cls,
        coach_or_path: Union[CoachState, str, Path],
        live: bool = False,
        save: bool = False,
    ) -> Tuple[CoachState, str, Dict[str, Any]]:
        if isinstance(coach_or_path, (str, Path)):
            coach_state = StateStore.load_state(CoachState, coach_or_path)
        else:
            coach_state = coach_or_path

        updated_state, md, diff = await CoachModeEngine.update_coach_memory(coach_state, live=live)
        if save:
            StateStore.save_state(updated_state)
        return updated_state, md, diff

    @classmethod
    async def run_full_pipeline(
        cls,
        skill_id: str = "direct_refutation",
        difficulty: str = "steady",
        user_side: str = "agree",
        user_arguments: Optional[List[str]] = None,
        live: bool = False,
        save: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes all 4 modules sequentially in isolation, passing state cleanly from one to the next:
        1. Topic Generator
        2. Debate Mode
        3. Reviewer (Scorer)
        4. Coach Mode (Opening Analysis & Memory Update)
        """
        t_pipeline_start = time.perf_counter()

        # Step 1: Generate Topics
        topic_state = await cls.run_topic_generation(
            TopicGeneratorInput(skill_id=skill_id, difficulty=difficulty, count=1),
            live=live,
            save=save,
        )
        selected_topic = topic_state.generated_topics[0]

        # Step 2: Simulate Debate
        debate_state = await DebateModeEngine.simulate_full_debate(
            topic=selected_topic.statement,
            user_side=user_side,
            skill_id=skill_id,
            difficulty=difficulty,
            user_arguments=user_arguments,
            live=live,
        )
        if save:
            StateStore.save_state(debate_state)

        # Step 3: Run Reviewer
        review_state = await cls.run_review(debate_state, live=live, save=save)

        # Step 4: Setup and Run Coach
        coach_state = StateStore.create_coach_from_review_and_debate(
            review_state=review_state,
            debate_state=debate_state,
        )
        coach_state, opening = await cls.run_coach_opening(coach_state, live=live, save=save)
        coach_state, updated_memory, memory_diff = await cls.run_coach_memory_update(coach_state, live=live, save=save)

        total_dur_ms = round((time.perf_counter() - t_pipeline_start) * 1000, 2)

        return {
            "topic_state": topic_state,
            "debate_state": debate_state,
            "review_state": review_state,
            "coach_state": coach_state,
            "total_duration_ms": total_dur_ms,
            "summary": {
                "motion": selected_topic.statement,
                "outcome": review_state.outcome,
                "stars": review_state.mastery_stars,
                "scores": {
                    "technique": review_state.score_technique.score if review_state.score_technique else None,
                    "grammar": review_state.score_grammar.score if review_state.score_grammar else None,
                    "vocabulary": review_state.score_vocabulary.score if review_state.score_vocabulary else None,
                    "delivery": review_state.score_delivery.score if review_state.score_delivery else None,
                },
                "opening_assessment": opening.overall_assessment,
                "memory_lines_added": memory_diff.get("lines_added", 0),
            },
        }
