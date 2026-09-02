// Core product types. The frontend contract is intentionally loose:
// optional fields everywhere so future backends can evolve freely.

export type SkillId =
  | "take_a_side"
  | "give_a_reason"
  | "back_it_up"
  | "counterpoint"
  | "counterargument"
  | "rebuttal"
  | "concession"
  | "devils_advocate"
  | "cross_examination"
  | "evidence"
  | "nuance";

export type Speaker = "user" | "opponent";

export type DebateTurn = {
  id: string;
  speaker: Speaker;
  /** Optional: a text-only backend may never send audio, a speech-to-speech backend may never send text. */
  text?: string;
  /** Optional playback info, never assumed to exist. */
  playback?: { available: boolean; durationSec?: number; audioUrl?: string };
  durationSec?: number;
  // Conversational metadata
  move?: string;
  requiresResponse?: boolean;
  addressedClaim?: string;
  conversationState?: "unresolved" | "advanced" | "ready_to_close";
  mediaAssetId?: string;
};

export type DebateSide = "agree" | "disagree";

export type Difficulty = "gentle" | "steady" | "sharp";

export type DebateSession = {
  id: string;
  topic: string;
  skillTarget: { id: SkillId | string; name: string; hint: string };
  difficulty: Difficulty;
  userSide: DebateSide;
  totalUserTurns: number;
  currentTurn: number;
  status: "active" | "finished" | "abandoned" | "error";
  turns: DebateTurn[];
  skillReminder: string;
  isOnboarding?: boolean;
};

export type DebateSetup = {
  topic: string;
  skillTarget: { id: SkillId | string; name: string; hint: string };
  skillReminder: string;
  difficulty: Difficulty;
  totalUserTurns: number;
  secondsPerTurn: number;
  opponentLines: string[]; // mock opponent responses, one per user turn
};

export type ScoreWithRubric = {
  score?: number | null;
  label: string;
  rubric: string;
};

/** Review contract — every field is defensive; treat as possibly absent. */
export type StarAssessment = {
  stars: 0 | 1 | 2 | 3;
  completed: boolean;
  skillDemonstrated: boolean;
  masteryNote?: string;
};

export type DebateReview = {
  sessionId?: string;
  outcome: "user_win" | "opponent_win" | "draw" | "undetermined";
  stars: StarAssessment;
  skillAssessment?: {
    targetSkill: SkillId | string;
    demonstrated: boolean;
    summary: string;
  };
  argumentFeedback?: {
    strength: string;
    improvement: string;
    insight?: string;
  };
  languageFeedback?: {
    pronunciation?: PronunciationPattern[];
    fluency?: { summary: string; trend?: string; score?: number };
    grammar?: { summary: string; examples?: string[] };
    vocabulary?: { summary: string; examples?: string[] };
    clarity?: { summary: string; score?: number };
  };
  xpEarned: number;
  streakExtended: boolean;
  nextLevelUnlocked?: boolean;
  topic: string;
  skillName: string;

  // 4 Integer Scores out of 10
  scoreTechnique?: ScoreWithRubric;
  scoreGrammar?: ScoreWithRubric;
  scoreVocabulary?: ScoreWithRubric;
  scoreDelivery?: ScoreWithRubric;
  strongestMoment?: string;
  improvementOpportunity?: string;
};

export type PronunciationPattern = {
  sound: string;
  heardIn?: string[];
  note: string;
  occurrences?: number;
  severity?: "minor" | "noticeable";
  timestampSec?: number;
};

export type PathNode = {
  id: SkillId;
  order: number;
  name: string;
  description: string;
  stars: 0 | 1 | 2 | 3;
  status: "complete" | "current" | "locked";
  topicId?: string;
  topicPreview?: string;
};

export type LearningPath = {
  levelName: string;
  levelNumber: number;
  nodes: PathNode[];
};

export type ProgressStats = {
  xp: number;
  streakDays: number;
  streakHistory: number[]; // last 7 days
  debatesCompleted: number;
  wins: number;
  losses: number;
  draws: number;
  skillMastery: { skill: string; level: "Strong" | "Improving" | "Developing" }[];
  pronunciationTrend?: string;
  fluencyTrend?: string;
};

export type OnboardingPreferences = {
  goals: string[];
  comfort: string;
  interests: string[];
  intensity: "easygoing" | "balanced" | "bring_it_on";
};

// ---------------------------------------------------------------------------
// Coaching System Types
// ---------------------------------------------------------------------------

export type QuickReply = {
  label: string;
  prompt: string;
};

export type OpeningAnalysis = {
  overallAssessment: string;
  mostImportantStrength: string;
  highestValueImprovement: string;
  concreteExample?: string;
  evidenceTurnNumber?: number;
  suggestedQuickReplies?: QuickReply[];
};

export type AudioEvidenceCard = {
  clipId: string;
  mediaAssetId: string;
  audioUrl: string;
  durationSec: number;
  sourceLabel: string;
  transcriptExcerpt: string;
  whatToNotice: string;
  turnNumber?: number;
  available?: boolean;
};

export type CoachMessage = {
  id: string;
  threadId: string;
  sender: "user" | "coach";
  messageType: "text" | "audio" | "opening_analysis" | "evidence_card";
  text?: string;
  mediaAssetId?: string;
  audioUrl?: string;
  durationSec?: number;
  evidenceClip?: AudioEvidenceCard;
  openingAnalysis?: OpeningAnalysis;
  quickReplies?: QuickReply[];
  processingState?: "recording" | "uploading" | "processing" | "ready" | "failed";
  createdAt?: string;
};

export type CoachThreadSummary = {
  id: string;
  sessionId?: string;
  threadType: "debate_review" | "general";
  title: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
  topic?: string;
  skillName?: string;
};

export type CoachThreadDetail = {
  thread: CoachThreadSummary;
  messages: CoachMessage[];
  debateSession?: DebateSession;
  debateReview?: DebateReview;
};

export type CoachHomeData = {
  activeFocus: string;
  focusDetails?: string;
  progressSummary: ProgressStats;
  presetQuestions: QuickReply[];
  recentDebateThreads: CoachThreadSummary[];
  generalThreads: CoachThreadSummary[];
};
