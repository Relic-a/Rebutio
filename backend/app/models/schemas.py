from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Frontend Contract Schemas
# ---------------------------------------------------------------------------

class OnboardingPreferencesSchema(BaseModel):
    goals: List[str] = Field(default_factory=list)
    comfort: str = ""
    interests: List[str] = Field(default_factory=list)
    intensity: Literal["easygoing", "balanced", "bring_it_on"] = "balanced"


class PathNodeSchema(BaseModel):
    id: str
    order: int
    name: str
    description: str
    stars: int = Field(ge=0, le=3)
    status: Literal["complete", "current", "locked"]
    topicPreview: Optional[str] = None


class LearningPathSchema(BaseModel):
    levelName: str
    levelNumber: int
    nodes: List[PathNodeSchema]


class BootstrapInfoSchema(BaseModel):
    onboarded: bool
    path: LearningPathSchema
    preferences: Optional[OnboardingPreferencesSchema] = None
    saveTranscripts: bool = False
    captionsEnabled: bool = True


class DebateTopicChoiceSchema(BaseModel):
    id: str
    topic: str
    skill: str
    difficulty: Literal["gentle", "steady", "sharp"] = "steady"
    turns: int = 4
    minutes: int = 6
    reminder: str = ""
    opponentLines: Optional[List[str]] = None


class DebateTurnPlaybackSchema(BaseModel):
    available: bool = True
    durationSec: Optional[float] = None
    audioUrl: Optional[str] = None


class DebateTurnSchema(BaseModel):
    id: str
    speaker: Literal["user", "opponent"]
    text: Optional[str] = None
    playback: Optional[DebateTurnPlaybackSchema] = None
    durationSec: Optional[float] = None


class SkillTargetSchema(BaseModel):
    id: str
    name: str
    hint: str


class DebateSessionSchema(BaseModel):
    id: str
    topic: str
    skillTarget: SkillTargetSchema
    difficulty: Literal["gentle", "steady", "sharp"]
    userSide: Literal["agree", "disagree"]
    totalUserTurns: int
    currentTurn: int
    status: Literal["active", "finished", "error"]
    turns: List[DebateTurnSchema]
    skillReminder: str


class DebateSetupSchema(BaseModel):
    topic: str
    skillTarget: SkillTargetSchema
    skillReminder: str
    difficulty: Literal["gentle", "steady", "sharp"]
    totalUserTurns: int
    secondsPerTurn: int = 0
    opponentLines: List[str] = Field(default_factory=list)


class StartDebateRequestSchema(BaseModel):
    topicId: Optional[str] = None
    side: Literal["agree", "disagree"] = "agree"
    onboarding: bool = False
    interests: Optional[List[str]] = None


class StartDebateResponseSchema(BaseModel):
    session: DebateSessionSchema
    setup: DebateSetupSchema


class SubmitTurnResponseSchema(BaseModel):
    userTurn: DebateTurnSchema
    opponentTurn: DebateTurnSchema
    nextUserTurnNumber: int
    finished: bool


class PronunciationPatternSchema(BaseModel):
    sound: str
    heardIn: Optional[List[str]] = None
    note: str
    occurrences: Optional[int] = None
    severity: Optional[Literal["minor", "noticeable"]] = "minor"
    timestampSec: Optional[float] = None


class FluencyFeedbackSchema(BaseModel):
    summary: str
    trend: Optional[str] = None
    score: Optional[int] = None


class DetailFeedbackSchema(BaseModel):
    summary: str
    examples: Optional[List[str]] = None
    score: Optional[int] = None


class LanguageFeedbackSchema(BaseModel):
    pronunciation: Optional[List[PronunciationPatternSchema]] = None
    fluency: Optional[FluencyFeedbackSchema] = None
    grammar: Optional[DetailFeedbackSchema] = None
    vocabulary: Optional[DetailFeedbackSchema] = None
    clarity: Optional[DetailFeedbackSchema] = None


class StarAssessmentSchema(BaseModel):
    stars: Literal[1, 2, 3] = 1
    completed: bool = True
    skillDemonstrated: bool = False
    masteryNote: Optional[str] = None


class SkillAssessmentSchema(BaseModel):
    targetSkill: str
    demonstrated: bool
    summary: str


class ArgumentFeedbackSchema(BaseModel):
    strength: str
    improvement: str
    insight: Optional[str] = None


class DebateReviewSchema(BaseModel):
    outcome: Literal["user_win", "opponent_win", "draw", "undetermined"]
    stars: StarAssessmentSchema
    skillAssessment: Optional[SkillAssessmentSchema] = None
    argumentFeedback: Optional[ArgumentFeedbackSchema] = None
    languageFeedback: Optional[LanguageFeedbackSchema] = None
    xpEarned: int = 60
    streakExtended: bool = False
    nextLevelUnlocked: Optional[bool] = None
    topic: str
    skillName: str


class ReviewFeedbackRequestSchema(BaseModel):
    sessionId: str
    verdict: Literal["disagree"] = "disagree"
    reason: Optional[str] = None


class SkillMasteryItemSchema(BaseModel):
    skill: str
    level: Literal["Strong", "Improving", "Developing"]


class ProgressStatsSchema(BaseModel):
    xp: int
    streakDays: int
    streakHistory: List[int]
    debatesCompleted: int
    wins: int
    losses: int
    draws: int
    skillMastery: List[SkillMasteryItemSchema]
    pronunciationTrend: Optional[str] = None
    fluencyTrend: Optional[str] = None


class SettingsUpdateSchema(BaseModel):
    saveTranscripts: Optional[bool] = None
    captionsEnabled: Optional[bool] = None
    intensity: Optional[Literal["easygoing", "balanced", "bring_it_on"]] = None


# ---------------------------------------------------------------------------
# AI Structured Output Schemas (Pydantic validation for LLMs)
# ---------------------------------------------------------------------------

class GeneratedTopicItem(BaseModel):
    id: str
    statement: str
    context: Optional[str] = None
    interest_tag: Optional[str] = None
    estimated_difficulty: Optional[Literal["gentle", "steady", "sharp"]] = "steady"


class GeneratedTopicsResponse(BaseModel):
    topics: List[GeneratedTopicItem]


class PhonemeEvidenceItem(BaseModel):
    phone: str
    start_ms: int
    end_ms: int


class TurnPhonemeEvidence(BaseModel):
    turn_number: int
    audio_duration_ms: int
    phonemes: List[PhonemeEvidenceItem] = Field(default_factory=list)
    client_response_delay_ms: int = 0
    words_per_minute: Optional[float] = None
    speech_gaps_count: Optional[int] = 0
    total_pause_duration_ms: Optional[int] = 0


class StructuredPronunciationFinding(BaseModel):
    sound: str
    heard_in: List[str] = Field(default_factory=list)
    note: str
    occurrences: int = 1
    severity: Literal["minor", "noticeable"] = "minor"
    confidence: float = 0.8
    reportable: bool = True


class StructuredFluencyFinding(BaseModel):
    summary: str
    trend: Optional[str] = "steady"
    hesitation_vs_thinking_note: Optional[str] = None
    score: Optional[int] = 75


class StructuredGrammarFinding(BaseModel):
    summary: str
    recurring_pattern: Optional[str] = None
    examples: List[str] = Field(default_factory=list)
    reportable: bool = True


class StructuredVocabularyFinding(BaseModel):
    summary: str
    examples: List[str] = Field(default_factory=list)
    suggested_alternatives: List[str] = Field(default_factory=list)


class StructuredClarityFinding(BaseModel):
    summary: str
    score: Optional[int] = 80


class MainLanguageAnalysisResult(BaseModel):
    pronunciation_findings: List[StructuredPronunciationFinding] = Field(default_factory=list)
    fluency_finding: Optional[StructuredFluencyFinding] = None
    grammar_finding: Optional[StructuredGrammarFinding] = None
    vocabulary_finding: Optional[StructuredVocabularyFinding] = None
    clarity_finding: Optional[StructuredClarityFinding] = None
    session_summary: str = ""
    top_coaching_points: List[str] = Field(default_factory=list)


class DebateReviewerResult(BaseModel):
    outcome: Literal["user_win", "opponent_win", "draw", "undetermined"]
    target_skill_demonstrated: bool
    mastery_stars: Literal[1, 2, 3] = 1
    mastery_note: Optional[str] = None
    skill_summary: str
    argument_strength: str
    argument_improvement: str
    strategic_insight: Optional[str] = None
