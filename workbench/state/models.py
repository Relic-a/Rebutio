from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 1. Topic Generator State
# ---------------------------------------------------------------------------

class TopicGeneratorInput(BaseModel):
    skill_id: str = "direct_refutation"
    skill_name: str = "Direct Refutation"
    difficulty: str = "steady"
    user_interests: List[str] = Field(default_factory=lambda: ["technology", "society", "ethics", "careers"])
    recent_topics: List[str] = Field(default_factory=list)
    compact_speech_findings: Optional[Dict[str, Any]] = None
    count: int = 3


class GeneratedTopic(BaseModel):
    id: str
    statement: str
    context: Optional[str] = None
    interest_tag: Optional[str] = None
    estimated_difficulty: Optional[str] = None
    skill_id: Optional[str] = None
    turns: int = 3
    minutes: int = 4
    reminder: Optional[str] = None


class TopicGeneratorState(BaseModel):
    inputs: TopicGeneratorInput = Field(default_factory=TopicGeneratorInput)
    generated_topics: List[GeneratedTopic] = Field(default_factory=list)
    prompt_messages: Optional[List[Dict[str, Any]]] = None
    raw_response: Optional[str] = None
    duration_ms: float = 0.0
    created_at: str = Field(default_factory=_now_iso)


# ---------------------------------------------------------------------------
# 2. Debate Mode State
# ---------------------------------------------------------------------------

class DebateTurn(BaseModel):
    turn_number: int
    speaker: str  # "user" | "opponent"
    text: str
    audio_metrics: Optional[Dict[str, Any]] = None  # phonemes, wpm, duration_sec, client_response_delay_ms
    duration_sec: float = 0.0
    timestamp: str = Field(default_factory=_now_iso)


class DebateState(BaseModel):
    session_id: str = Field(default_factory=lambda: f"sess-{uuid.uuid4().hex[:8]}")
    topic: str
    user_side: str = "agree"  # "agree" | "disagree"
    opponent_side: str = "disagree"
    skill_id: str = "direct_refutation"
    skill_name: str = "Direct Refutation"
    difficulty: str = "steady"
    intensity: str = "balanced"  # "easygoing" | "balanced" | "bring_it_on"
    total_turns: int = 3
    current_turn: int = 1
    status: str = "not_started"  # "not_started" | "active" | "review_pending" | "finished"
    turns: List[DebateTurn] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    is_closing_statement: bool = False
    closing_reason: Optional[str] = None
    last_opponent_prompt: Optional[List[Dict[str, Any]]] = None
    last_opponent_raw: Optional[str] = None
    last_latency_ms: float = 0.0
    created_at: str = Field(default_factory=_now_iso)

    @property
    def user_turns(self) -> List[DebateTurn]:
        return [t for t in self.turns if t.speaker == "user"]

    @property
    def opponent_turns(self) -> List[DebateTurn]:
        return [t for t in self.turns if t.speaker == "opponent"]

    def to_transcript_dicts(self) -> List[Dict[str, Any]]:
        return [
            {
                "speaker": t.speaker,
                "turn_number": t.turn_number,
                "text": t.text,
                "duration_sec": t.duration_sec,
                "audio_available": bool(t.audio_metrics),
            }
            for t in self.turns
        ]


# ---------------------------------------------------------------------------
# 3. Reviewer (Scorer) State
# ---------------------------------------------------------------------------

class ScoreCard(BaseModel):
    score: Optional[int] = None
    label: str
    rubric: str


class EvidenceAssessmentData(BaseModel):
    has_sufficient_evidence: bool = True
    has_sufficient_delivery_evidence: bool = False
    user_turns_count: int = 0
    substantive_turns_count: int = 0
    total_user_words: int = 0
    insufficient_reason: Optional[str] = None


class ReviewState(BaseModel):
    session_id: str
    topic: str
    user_side: str = "agree"
    opponent_side: str = "disagree"
    skill_id: str = "direct_refutation"
    skill_name: str = "Direct Refutation"
    difficulty: str = "steady"
    evidence_assessment: EvidenceAssessmentData = Field(default_factory=EvidenceAssessmentData)
    outcome: str = "undetermined"  # "user_win" | "opponent_win" | "draw" | "undetermined"
    mastery_stars: int = 0  # 0, 1, 2, 3
    completed: bool = False
    skill_demonstrated: bool = False
    mastery_note: Optional[str] = None
    skill_summary: Optional[str] = None
    score_technique: Optional[ScoreCard] = None
    score_grammar: Optional[ScoreCard] = None
    score_vocabulary: Optional[ScoreCard] = None
    score_delivery: Optional[ScoreCard] = None
    strongest_moment: Optional[str] = None
    improvement_opportunity: Optional[str] = None
    argument_feedback: Optional[Dict[str, Any]] = None  # strength, improvement, insight
    language_feedback: Optional[Dict[str, Any]] = None  # pronunciation, fluency, grammar, vocabulary, clarity
    raw_reviewer_response: Optional[Dict[str, Any]] = None
    raw_language_response: Optional[Dict[str, Any]] = None
    prompt_messages_reviewer: Optional[List[Dict[str, Any]]] = None
    prompt_messages_language: Optional[List[Dict[str, Any]]] = None
    duration_ms: float = 0.0
    created_at: str = Field(default_factory=_now_iso)


# ---------------------------------------------------------------------------
# 4. Coach Mode State
# ---------------------------------------------------------------------------

class CoachOpeningAnalysis(BaseModel):
    overall_assessment: str
    most_important_strength: str
    highest_value_improvement: str
    concrete_example: Optional[str] = None
    evidence_turn_number: Optional[int] = None
    suggested_quick_replies: List[str] = Field(default_factory=list)
    recommended_audio_clip: Optional[Dict[str, Any]] = None


class CoachMessageItem(BaseModel):
    id: str = Field(default_factory=lambda: f"msg-{uuid.uuid4().hex[:8]}")
    sender: str  # "coach" | "user"
    message_type: str = "text"  # "text" | "audio" | "opening_analysis" | "evidence_card"
    text: str
    structured_data: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    created_at: str = Field(default_factory=_now_iso)


class CoachState(BaseModel):
    user_id: str = "workbench-test-user"
    user_preferences: Dict[str, Any] = Field(default_factory=lambda: {"intensity": "balanced"})
    speech_profile: Dict[str, Any] = Field(default_factory=dict)
    coach_memory_markdown: str = ""
    debate_state: Optional[DebateState] = None
    review_state: Optional[ReviewState] = None
    opening_analysis: Optional[CoachOpeningAnalysis] = None
    thread_messages: List[CoachMessageItem] = Field(default_factory=list)
    active_focus: Optional[str] = None
    focus_details: Optional[str] = None
    memory_update_diff: Optional[Dict[str, Any]] = None  # previous, updated, changes_summary
    last_coach_prompt: Optional[List[Dict[str, Any]]] = None
    last_coach_raw: Optional[str] = None
    last_latency_ms: float = 0.0
    created_at: str = Field(default_factory=_now_iso)
