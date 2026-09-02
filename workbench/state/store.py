from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar, Union
from pydantic import BaseModel

from workbench.state.models import (
    CoachMessageItem,
    CoachOpeningAnalysis,
    CoachState,
    DebateState,
    DebateTurn,
    EvidenceAssessmentData,
    GeneratedTopic,
    ReviewState,
    TopicGeneratorInput,
    TopicGeneratorState,
)

T = TypeVar("T", bound=BaseModel)

BASE_DIR = Path(__file__).resolve().parent.parent
SAVED_DIR = BASE_DIR / "saved_states"
PRESETS_DIR = BASE_DIR / "state" / "presets"


class StateStore:
    """
    Manages loading, saving, listing, and transforming states for iterative workbench testing.
    """

    @staticmethod
    def ensure_directories():
        for sub in ["topics", "debates", "reviews", "coach"]:
            (SAVED_DIR / sub).mkdir(parents=True, exist_ok=True)
            (PRESETS_DIR / sub).mkdir(parents=True, exist_ok=True)

    @classmethod
    def save_state(cls, state: BaseModel, filename: Optional[str] = None, category: Optional[str] = None) -> Path:
        cls.ensure_directories()
        cat = category or cls._infer_category(state)
        target_dir = SAVED_DIR / cat

        if not filename:
            name = getattr(state, "session_id", None) or getattr(state, "user_id", None) or "state"
            filename = f"{name}.json"
        elif not filename.endswith(".json"):
            filename = f"{filename}.json"

        target_path = target_dir / filename
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(state.model_dump_json(indent=2))
        return target_path

    @classmethod
    def load_state(cls, model_cls: Type[T], path_or_name: Union[str, Path]) -> T:
        p = Path(path_or_name)
        if not p.exists():
            # Try searching in saved_states or presets
            candidates = [
                SAVED_DIR / p,
                PRESETS_DIR / p,
                SAVED_DIR / f"{p}.json",
                PRESETS_DIR / f"{p}.json",
            ]
            for cat in ["topics", "debates", "reviews", "coach"]:
                candidates.extend([
                    SAVED_DIR / cat / p,
                    PRESETS_DIR / cat / p,
                    SAVED_DIR / cat / f"{p}.json",
                    PRESETS_DIR / cat / f"{p}.json",
                ])

            found = next((c for c in candidates if c.exists() and c.is_file()), None)
            if not found:
                raise FileNotFoundError(f"State file not found: {path_or_name}")
            p = found

        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return model_cls.model_validate(data)

    @classmethod
    def list_saved_states(cls, category: Optional[str] = None) -> Dict[str, List[Path]]:
        cls.ensure_directories()
        categories = [category] if category else ["topics", "debates", "reviews", "coach"]
        res: Dict[str, List[Path]] = {}
        for cat in categories:
            cat_dir = SAVED_DIR / cat
            if cat_dir.exists():
                res[cat] = sorted(cat_dir.glob("*.json"))
            else:
                res[cat] = []
        return res

    @classmethod
    def list_presets(cls, category: Optional[str] = None) -> Dict[str, List[Path]]:
        cls.ensure_directories()
        categories = [category] if category else ["topics", "debates", "reviews", "coach"]
        res: Dict[str, List[Path]] = {}
        for cat in categories:
            cat_dir = PRESETS_DIR / cat
            if cat_dir.exists():
                res[cat] = sorted(cat_dir.glob("*.json"))
            else:
                res[cat] = []
        return res

    @staticmethod
    def _infer_category(state: BaseModel) -> str:
        if isinstance(state, TopicGeneratorState):
            return "topics"
        if isinstance(state, DebateState):
            return "debates"
        if isinstance(state, ReviewState):
            return "reviews"
        if isinstance(state, CoachState):
            return "coach"
        return "misc"

    # -----------------------------------------------------------------------
    # State Handoff Constructors
    # -----------------------------------------------------------------------

    @staticmethod
    def create_debate_from_topic(
        topic: Union[GeneratedTopic, Dict[str, Any], str],
        user_side: str = "agree",
        intensity: str = "balanced",
        total_turns: int = 3,
        skill_id: Optional[str] = None,
        skill_name: Optional[str] = None,
        difficulty: Optional[str] = None,
    ) -> DebateState:
        """
        Takes a generated topic and initializes a clean DebateState ready for turn 1.
        """
        if isinstance(topic, str):
            statement = topic
            s_id = skill_id or "direct_refutation"
            s_name = skill_name or "Direct Refutation"
            diff = difficulty or "steady"
            t_turns = total_turns
        elif isinstance(topic, GeneratedTopic):
            statement = topic.statement
            s_id = topic.skill_id or skill_id or "direct_refutation"
            s_name = skill_name or s_id.replace("_", " ").title()
            diff = topic.estimated_difficulty or difficulty or "steady"
            t_turns = topic.turns or total_turns
        else:
            statement = topic.get("statement") or topic.get("topic") or "Debate Topic"
            s_id = topic.get("skill_id") or topic.get("skill") or skill_id or "direct_refutation"
            s_name = skill_name or s_id.replace("_", " ").title()
            diff = topic.get("difficulty") or difficulty or "steady"
            t_turns = topic.get("turns") or total_turns

        opp_side = "disagree" if user_side == "agree" else "agree"

        return DebateState(
            topic=statement,
            user_side=user_side,
            opponent_side=opp_side,
            skill_id=s_id,
            skill_name=s_name,
            difficulty=diff,
            intensity=intensity,
            total_turns=t_turns,
            current_turn=1,
            status="not_started",
            turns=[],
        )

    @staticmethod
    def create_coach_from_review_and_debate(
        review_state: ReviewState,
        debate_state: Optional[DebateState] = None,
        user_id: str = "workbench-test-user",
        previous_memory_markdown: str = "",
    ) -> CoachState:
        """
        Takes a completed ReviewState (+ DebateState) and creates a CoachState ready for coaching.
        """
        initial_memory = previous_memory_markdown or (
            "# Rebutio Coach Memory\n\n"
            "## User Preferences & Goals\n"
            "- Goal: Speak concisely and counter opposing claims directly.\n"
            "- Intensity preference: Balanced.\n\n"
            "## Historical Summary\n"
            "- Recurring strength: Articulates main point cleanly.\n"
            "- Recurring focus: Pacing and supporting evidence.\n\n"
            "## Recent Debates\n"
        )

        return CoachState(
            user_id=user_id,
            coach_memory_markdown=initial_memory,
            debate_state=debate_state,
            review_state=review_state,
            thread_messages=[],
        )
