// ============================================================
// Frontend-facing application service boundary.
// Components consume this interface only — never a specific
// backend, provider, or transport.
// ============================================================

import type {
  DebateReview,
  DebateSetup,
  DebateSession,
  DebateSide,
  LearningPath,
  OnboardingPreferences,
  ProgressStats,
} from "@/lib/types";
import {
  firstSparByInterest,
  mockDebateTopics,
  mockDrawReview,
  mockLearningPath,
  mockLostButThreeStars,
  mockProgressStats,
  type DebateTopicFixture,
} from "@/lib/mock/fixtures";

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

export type BootstrapInfo = {
  onboarded: boolean;
  path: LearningPath;
  preferences?: OnboardingPreferences;
  saveTranscripts?: boolean;
  captionsEnabled?: boolean;
};

export type AppService = {
  getAppBootstrap(): Promise<BootstrapInfo>;
  saveOnboardingPreferences(prefs: OnboardingPreferences): Promise<void>;
  getLearningPath(): Promise<LearningPath>;
  getDebateChoices(): Promise<DebateTopicFixture[]>;
  /** Returns full setup for a debate; the UI renders whatever it receives. */
  startDebate(opts: {
    topicId?: string;
    side: DebateSide;
    onboarding?: boolean;
    interests?: string[];
  }): Promise<{ session: DebateSession; setup: DebateSetup }>;
  /**
   * Submits a recorded (or text) turn. Returns the opponent's next turn.
   */
  submitUserTurn(
    session: DebateSession,
    turn?: { audio?: Blob; transcript?: string; clientResponseDelayMs?: number }
  ): Promise<{
    userTurn: DebateSession["turns"][number];
    opponentTurn: DebateSession["turns"][number];
    nextUserTurnNumber: number;
    finished: boolean;
  }>;
  /** Semantic session observation hook */
  observeDebateSession(sessionId: string, onEvent: (event: { type: string; data?: any }) => void): () => void;
  finishDebate(session: DebateSession): Promise<void>;
  getDebateReview(sessionId: string): Promise<DebateReview>;
  submitReviewFeedback(feedback: { sessionId: string; verdict: "disagree"; reason?: string }): Promise<void>;
  getProgress(): Promise<ProgressStats>;
};

// ---------------------------------------------------------------------------
// HTTP Implementation (Production / Local Backend)
// ---------------------------------------------------------------------------

export function createHttpService(baseUrl: string = ""): AppService {
  const apiBase = baseUrl ? baseUrl.replace(/\/+$/, "") : "";

  async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const url = `${apiBase}${path}`;
    const res = await fetch(url, {
      ...options,
      credentials: "include",
      headers: {
        Accept: "application/json",
        ...options.headers,
      },
    });

    if (!res.ok) {
      const errText = await res.text().catch(() => "");
      throw new Error(`API error ${res.status}: ${errText || res.statusText}`);
    }

    return res.json();
  }

  return {
    async getAppBootstrap() {
      return request<BootstrapInfo>("/api/bootstrap");
    },

    async saveOnboardingPreferences(prefs: OnboardingPreferences) {
      await request("/api/onboarding/preferences", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(prefs),
      });
    },

    async getLearningPath() {
      return request<LearningPath>("/api/path");
    },

    async getDebateChoices() {
      const choices = await request<DebateTopicFixture[]>("/api/debates/choices");
      return choices.length > 0 ? choices : mockDebateTopics;
    },

    async startDebate(opts) {
      const res = await request<{ session: DebateSession; setup: DebateSetup }>("/api/debates/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topicId: opts.topicId,
          side: opts.side,
          onboarding: opts.onboarding ?? false,
          interests: opts.interests,
        }),
      });
      return res;
    },

    async submitUserTurn(session, turn) {
      const formData = new FormData();
      if (turn?.audio) {
        formData.append("audio", turn.audio, "user_turn.webm");
      }
      if (turn?.transcript) {
        formData.append("transcript", turn.transcript);
      }
      if (turn?.clientResponseDelayMs !== undefined) {
        formData.append("client_response_delay_ms", String(turn.clientResponseDelayMs));
      }
      formData.append("turn_index", String(session.currentTurn));

      const res = await fetch(`${apiBase}/api/sessions/${session.id}/turns`, {
        method: "POST",
        body: formData,
        credentials: "include",
      });

      if (!res.ok) {
        const errText = await res.text().catch(() => "");
        throw new Error(`Turn submission failed: ${errText || res.statusText}`);
      }

      const data = await res.json();
      // Ensure opponent turn playback audioUrl is fully qualified if needed
      if (data.opponentTurn?.playback?.audioUrl && apiBase) {
        data.opponentTurn.playback.audioUrl = `${apiBase}${data.opponentTurn.playback.audioUrl}`;
      }
      return data;
    },

    observeDebateSession(sessionId, onEvent) {
      if (typeof window === "undefined" || typeof EventSource === "undefined") {
        return () => {};
      }

      try {
        const es = new EventSource(`${apiBase}/api/sessions/${sessionId}/events`, {
          withCredentials: true,
        });

        es.onmessage = (e) => {
          try {
            const parsed = JSON.parse(e.data);
            onEvent(parsed);
          } catch {}
        };

        es.onerror = () => {
          es.close();
        };

        return () => es.close();
      } catch {
        return () => {};
      }
    },

    async finishDebate(session) {
      await request(`/api/sessions/${session.id}/finish`, {
        method: "POST",
      }).catch(() => {});
    },

    async getDebateReview(sessionId) {
      return request<DebateReview>(`/api/sessions/${sessionId}/review`);
    },

    async submitReviewFeedback(feedback) {
      await request(`/api/sessions/${feedback.sessionId}/review-feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(feedback),
      });
    },

    async getProgress() {
      return request<ProgressStats>("/api/progress");
    },
  };
}

// ---------------------------------------------------------------------------
// Mock Implementation (Behind development flag)
// ---------------------------------------------------------------------------

export function createMockService(): AppService {
  return {
    async getAppBootstrap() {
      await delay(300);
      return { onboarded: false, path: mockLearningPath };
    },
    async saveOnboardingPreferences() {
      await delay(400);
    },
    async getLearningPath() {
      await delay(250);
      return mockLearningPath;
    },
    async getDebateChoices() {
      await delay(250);
      return mockDebateTopics;
    },
    async startDebate({ topicId, side, onboarding, interests }) {
      await delay(onboarding ? 600 : 500);
      let topic: DebateTopicFixture | undefined;
      if (onboarding) {
        const key = interests?.find((i) => firstSparByInterest[i]);
        topic = mockDebateTopics.find((t) => t.id === (key && firstSparByInterest[key])) ?? mockDebateTopics.find((t) => t.id === "social-media");
      } else {
        topic = mockDebateTopics.find((t) => t.id === topicId) ?? mockDebateTopics[0];
      }
      const total = onboarding ? 3 : topic!.turns;
      const session: DebateSession = {
        id: `session-${Date.now()}`,
        topic: topic!.topic,
        skillTarget: { id: topic!.skill, name: skillName(topic!.skill), hint: skillHint(topic!.skill) },
        difficulty: topic!.difficulty,
        userSide: side,
        totalUserTurns: total,
        currentTurn: 1,
        status: "active",
        turns: [],
        skillReminder: topic!.reminder,
      };
      const setup: DebateSetup = {
        topic: topic!.topic,
        skillTarget: session.skillTarget,
        skillReminder: topic!.reminder,
        difficulty: topic!.difficulty,
        totalUserTurns: total,
        secondsPerTurn: 0,
        opponentLines: onboarding ? topic!.opponentLines.slice(0, total) : topic!.opponentLines,
      };
      return { session, setup };
    },
    async submitUserTurn(session, turn) {
      const thinking = session.currentTurn === 1 ? 2600 : 2100 + Math.random() * 1200;
      await delay(thinking);
      const userTurn = { id: `t-u-${session.currentTurn}`, speaker: "user" as const, text: turn?.transcript, playback: turn?.audio ? { available: true } : undefined };
      const fixture = mockDebateTopics.find((t) => t.topic === session.topic);
      const line = fixture?.opponentLines[session.currentTurn - 1];
      const opponentTurn = { id: `t-o-${session.currentTurn}`, speaker: "opponent" as const, text: line };
      const finished = session.currentTurn >= session.totalUserTurns;
      return {
        userTurn,
        opponentTurn,
        nextUserTurnNumber: Math.min(session.currentTurn + 1, session.totalUserTurns),
        finished,
      };
    },
    observeDebateSession(_sessionId, onEvent) {
      const timer = setTimeout(() => onEvent({ type: "session.started" }), 200);
      return () => clearTimeout(timer);
    },
    async finishDebate() {
      await delay(300);
    },
    async getDebateReview(sessionId) {
      await delay(3400);
      const n = Math.abs(hash(sessionId)) % 3;
      if (n === 0) return { ...mockLostButThreeStars, topic: currentSession?.topic ?? mockLostButThreeStars.topic, skillName: currentSession?.skillTarget.name ?? mockLostButThreeStars.skillName };
      if (n === 1) return { ...mockDrawReview, topic: currentSession?.topic ?? mockDrawReview.topic, skillName: currentSession?.skillTarget.name ?? mockDrawReview.skillName };
      return { ...mockLostButThreeStars, outcome: "user_win", topic: currentSession?.topic ?? mockLostButThreeStars.topic, skillName: currentSession?.skillTarget.name ?? mockLostButThreeStars.skillName, xpEarned: 150, stars: { ...mockLostButThreeStars.stars, stars: 2, masteryNote: "You addressed the counterargument directly." } };
    },
    async submitReviewFeedback() {
      await delay(500);
    },
    async getProgress() {
      await delay(250);
      return mockProgressStats;
    },
  };
}

let currentSession: DebateSession | null = null;
export function noteCurrentSession(s: DebateSession) {
  currentSession = s;
}

function hash(s: string) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return h;
}

export function skillName(id: string): string {
  const map: Record<string, string> = {
    take_a_side: "Take a Side",
    give_a_reason: "Give a Reason",
    back_it_up: "Back It Up",
    counterpoint: "Counterpoint",
    rebuttal: "Rebuttal",
    concession: "Concession",
    devils_advocate: "Devil's Advocate",
    cross_examination: "Cross Examination",
    evidence: "Evidence",
    nuance: "Nuance",
    counterargument: "Counterargument",
  };
  return map[id] ?? id;
}

function skillHint(id: string): string {
  const map: Record<string, string> = {
    take_a_side: "Pick a side and hold it.",
    give_a_reason: "Give one clear reason for your side.",
    back_it_up: "Support your reason with a concrete example.",
    counterpoint: "Make a counterargument, not just a defense.",
    rebuttal: "Respond directly to their strongest point.",
    concession: "Concede part of their argument without dropping yours.",
    devils_advocate: "Defend a position you don't personally agree with.",
    cross_examination: "Press their weakest point with a direct question.",
    evidence: "Support your point with a concrete example.",
    nuance: "Weigh two competing principles against each other.",
    counterargument: "Make a counterargument, not just a defense.",
  };
  return map[id] ?? "Respond to what they actually said.";
}

const isMock = process.env.NEXT_PUBLIC_USE_MOCK_API === "true";
const apiHost = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const appService: AppService = isMock ? createMockService() : createHttpService(apiHost);
