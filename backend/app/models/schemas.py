from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field



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
    topicId: Optional[str] = None
    topicPreview: Optional[str] = None


class LearningPathSchema(BaseModel):
    levelName: str
    levelNumber: int
    nodes: List[PathNodeSchema]


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
    # Conversational metadata
    move: Optional[str] = None  # challenge_assumption | ask_clarification | counterexample | request_evidence | concede_and_press | answer_user_question | closing_challenge
    requiresResponse: bool = True
    addressedClaim: Optional[str] = None
    conversationState: Optional[Literal["unresolved", "advanced", "ready_to_close"]] = "unresolved"
    mediaAssetId: Optional[str] = None


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
    status: Literal["active", "finished", "abandoned", "error"]
    turns: List[DebateTurnSchema]
    skillReminder: str
    isOnboarding: bool = False


class BootstrapInfoSchema(BaseModel):
    onboarded: bool
    path: LearningPathSchema
    preferences: Optional[OnboardingPreferencesSchema] = None
    saveTranscripts: bool = False
    captionsEnabled: bool = True
    activeSession: Optional[DebateSessionSchema] = None


class DebateTopicChoiceSchema(BaseModel):
    id: str
    topic: str
    skill: str
    difficulty: Literal["gentle", "steady", "sharp"] = "steady"
    turns: int = 4
    minutes: int = 6
    reminder: str = ""
    opponentLines: Optional[List[str]] = None


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
    opponentTurn: Optional[DebateTurnSchema] = None
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


class ScoreWithRubricSchema(BaseModel):
    score: int = Field(ge=1, le=10)
    label: str
    rubric: str


class DebateReviewSchema(BaseModel):
    sessionId: Optional[str] = None
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

    # Concise Results 4 Integer Scores out of 10
    scoreTechnique: ScoreWithRubricSchema = Field(
        default_factory=lambda: ScoreWithRubricSchema(
            score=8,
            label="Debate technique",
            rubric="Directly addressed opposing claims and provided reasoned counterpoints.",
        )
    )
    scoreGrammar: ScoreWithRubricSchema = Field(
        default_factory=lambda: ScoreWithRubricSchema(
            score=8,
            label="Grammar",
            rubric="Clean sentence structures with minimal syntactic friction under pressure.",
        )
    )
    scoreVocabulary: ScoreWithRubricSchema = Field(
        default_factory=lambda: ScoreWithRubricSchema(
            score=8,
            label="Vocabulary",
            rubric="Appropriate and precise word choices tailored to the debate motion.",
        )
    )
    scoreDelivery: ScoreWithRubricSchema = Field(
        default_factory=lambda: ScoreWithRubricSchema(
            score=8,
            label="Delivery",
            rubric="Steady speech rate and natural conversational pauses.",
        )
    )
    strongestMoment: str = "Your direct refutation of the core premise held firm."
    improvementOpportunity: str = "Introduce your main supporting evidence earlier in the turn."


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


class DebateHistoryItemSchema(BaseModel):
    sessionId: str
    topic: str
    skillName: str
    difficulty: str
    outcome: str
    stars: int
    createdAt: str
    transcriptsSaved: bool


class DebateHistoryDetailSchema(BaseModel):
    session: DebateSessionSchema
    review: Optional[DebateReviewSchema] = None
    transcriptsSaved: bool


# ---------------------------------------------------------------------------
# Coaching Chat & Media Contracts
# ---------------------------------------------------------------------------

class QuickReplySchema(BaseModel):
    label: str
    prompt: str


class OpeningAnalysisSchema(BaseModel):
    overallAssessment: str
    mostImportantStrength: str
    highestValueImprovement: str
    concreteExample: Optional[str] = None
    evidenceTurnNumber: Optional[int] = None
    suggestedQuickReplies: List[QuickReplySchema] = Field(default_factory=list)


class AudioEvidenceCardSchema(BaseModel):
    clipId: str
    mediaAssetId: str
    audioUrl: str
    durationSec: float
    sourceLabel: str  # e.g. "Debate · Turn 3" | "Practice attempt"
    transcriptExcerpt: str
    whatToNotice: str
    turnNumber: Optional[int] = None
    available: bool = True


class CoachMessageSchema(BaseModel):
    id: str
    threadId: str
    sender: Literal["user", "coach"]
    messageType: Literal["text", "audio", "opening_analysis", "evidence_card"]
    text: Optional[str] = None
    mediaAssetId: Optional[str] = None
    audioUrl: Optional[str] = None
    durationSec: Optional[float] = None
    evidenceClip: Optional[AudioEvidenceCardSchema] = None
    openingAnalysis: Optional[OpeningAnalysisSchema] = None
    quickReplies: Optional[List[QuickReplySchema]] = None
    processingState: Literal["recording", "uploading", "processing", "ready", "failed"] = "ready"
    createdAt: str


class CoachThreadSummarySchema(BaseModel):
    id: str
    sessionId: Optional[str] = None
    threadType: Literal["debate_review", "general"]
    title: str
    createdAt: str
    updatedAt: str
    messageCount: int = 0
    topic: Optional[str] = None
    skillName: Optional[str] = None


class CoachThreadDetailSchema(BaseModel):
    thread: CoachThreadSummarySchema
    messages: List[CoachMessageSchema]
    debateSession: Optional[DebateSessionSchema] = None
    debateReview: Optional[DebateReviewSchema] = None


class CoachHomeSchema(BaseModel):
    activeFocus: str
    focusDetails: Optional[str] = None
    progressSummary: ProgressStatsSchema
    presetQuestions: List[QuickReplySchema]
    recentDebateThreads: List[CoachThreadSummarySchema]
    generalThreads: List[CoachThreadSummarySchema]


class SendTextMessageRequestSchema(BaseModel):
    text: str


class CoachMemorySchema(BaseModel):
    userId: str
    memoryMarkdown: str
    revision: int
    updatedAt: str


class MemoryCorrectionRequestSchema(BaseModel):
    correctionText: str
    action: Optional[Literal["update", "dismiss", "reject_feedback"]] = "update"
    patternId: Optional[str] = None
    patternType: Optional[str] = None
    label: Optional[str] = None


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
    score_technique: int = 8
    score_grammar: int = 8
    score_vocabulary: int = 8
    score_delivery: int = 8
    score_technique_rubric: str = "Directly addressed opposing arguments with structured counterpoints."
    score_grammar_rubric: str = "Grammatically clear and coherent speech under time pressure."
    score_vocabulary_rubric: str = "Appropriate vocabulary and phrase variation."
    score_delivery_rubric: str = "Consistent pacing and fluent spoken delivery."
    strongest_moment: str = "Your rebuttal in turn 2 addressed the opposing premise directly."
    improvement_opportunity: str = "State your core claim earlier before elaborate setup."


class OpponentMoveResponse(BaseModel):
    text: str
    move: Literal[
        "challenge_assumption",
        "ask_clarification",
        "counterexample",
        "request_evidence",
        "concede_and_press",
        "answer_user_question",
        "closing_challenge",
    ] = "challenge_assumption"
    requires_response: bool = True
    addressed_claim: str = "the previous point"
    conversation_state: Literal["unresolved", "advanced", "ready_to_close"] = "unresolved"


class CoachOpeningAnalysisResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    overall_assessment: str
    most_important_strength: str = Field(default="You held your ground with strong counterpoints.", alias="mostImportantStrength")
    highest_value_improvement: str = Field(default="Lead with your main claim earlier.", alias="highestValueImprovement")
    concrete_example: Optional[str] = None
    evidence_turn_number: Optional[int] = None
    suggested_quick_replies: List[str] = Field(
        default_factory=lambda: [
            "Show me another example",
            "How should I phrase it?",
            "Was my grammar a problem?",
            "What should I practice?",
            "Let me try that again",
        ]
    )



class CoachTurnResponse(BaseModel):
    reply_text: str
    requested_tool: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    evidence_card: Optional[Dict[str, Any]] = None
    quick_replies: List[str] = Field(default_factory=list)
    memory_update: Optional[Dict[str, Any]] = None
