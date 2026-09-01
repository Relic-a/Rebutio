// ============================================================
// Frontend-facing application service boundary.
// Components consume this interface only — never a specific
// backend, provider, or transport.
// ============================================================

import { createClient } from "@insforge/sdk";
import type {
  CoachHomeData,
  CoachMessage,
  CoachThreadDetail,
  CoachThreadSummary,
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
import { logger } from "@/lib/logger";

export const insforge = createClient({
  baseUrl: process.env.NEXT_PUBLIC_INSFORGE_URL || "https://yb269bge.us-east.insforge.app",
  anonKey: process.env.NEXT_PUBLIC_INSFORGE_ANON_KEY || "anon_5042180029b5d24c41a999b3b07eabd76b6f740aa6749b5358bd95e4d6fe42b5",
});

export async function getAuthHeaders(): Promise<Record<string, string>> {
  try {
    const token = await insforge.getHttpClient().getValidAccessToken();
    if (token) {
      return { Authorization: `Bearer ${token}` };
    }
    // Check if SDK headers already have Authorization set
    const clientHeaders = insforge.getHttpClient().getHeaders();
    if (clientHeaders["Authorization"] || clientHeaders["authorization"]) {
      return { Authorization: clientHeaders["Authorization"] || clientHeaders["authorization"] };
    }
  } catch {
    // Non-blocking
  }
  return {};
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

export type BootstrapInfo = {
  onboarded: boolean;
  path: LearningPath;
  preferences?: OnboardingPreferences;
  saveTranscripts?: boolean;
  captionsEnabled?: boolean;
  activeSession?: DebateSession | null;
};

export type AppService = {
  getAppBootstrap(): Promise<BootstrapInfo>;
  saveOnboardingPreferences(prefs: OnboardingPreferences): Promise<void>;
  getLearningPath(): Promise<LearningPath>;
  getDebateChoices(): Promise<DebateTopicFixture[]>;
  getSession(sessionId: string): Promise<DebateSession>;
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
    opponentTurn?: DebateSession["turns"][number] | null;
    nextUserTurnNumber: number;
    finished: boolean;
  }>;
  /** Semantic session observation hook */
  observeDebateSession(sessionId: string, onEvent: (event: { type: string; data?: any }) => void): () => void;
  finishDebate(session: DebateSession): Promise<void>;
  getDebateReview(sessionId: string): Promise<DebateReview>;
  submitReviewFeedback(feedback: { sessionId: string; verdict: "disagree"; reason?: string }): Promise<void>;
  getProgress(): Promise<ProgressStats>;

  // Coaching System Endpoints
  getCoachHome(): Promise<CoachHomeData>;
  getSessionCoachThread(sessionId: string): Promise<CoachThreadDetail>;
  createGeneralCoachThread(text: string): Promise<CoachThreadDetail>;
  getCoachThreadDetail(threadId: string): Promise<CoachThreadDetail>;
  sendCoachTextMessage(threadId: string, text: string): Promise<CoachMessage>;
  sendCoachAudioMessage(threadId: string, audio: Blob): Promise<{ userMessage: CoachMessage; coachMessage: CoachMessage }>;
  correctCoachingMemory(correction: {
    patternId?: string;
    patternType?: string;
    label?: string;
    correctionText: string;
    action?: "update" | "dismiss" | "reject_feedback";
  }): Promise<any>;
  getMediaAssetAudioUrl(assetId: string): string;
  getClipAudioUrl(clipId: string): string;
};

// ---------------------------------------------------------------------------
// HTTP Implementation (Production / Local Backend)
// ---------------------------------------------------------------------------

function parseErrorDetail(errText: string, defaultText: string): string {
  try {
    const parsed = JSON.parse(errText);
    if (typeof parsed.detail === "string" && parsed.detail.trim()) {
      return parsed.detail.trim();
    }
    if (typeof parsed.message === "string" && parsed.message.trim()) {
      return parsed.message.trim();
    }
  } catch {
    // not JSON
  }
  return errText || defaultText;
}

export function createHttpService(baseUrl: string = ""): AppService {
  const apiBase = baseUrl ? baseUrl.replace(/\/+$/, "") : "";

  async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const url = `${apiBase}${path}`;
    const authHeaders = await getAuthHeaders();
    try {
      const res = await fetch(url, {
        ...options,
        credentials: "include",
        headers: {
          Accept: "application/json",
          ...authHeaders,
          ...options.headers,
        },
      });

      const reqId = res.headers.get("x-request-id");
      if (reqId) {
        logger.setRequestId(reqId);
      }

      if (!res.ok) {
        const errText = await res.text().catch(() => "");
        const errMsg = parseErrorDetail(errText, res.statusText || `Request failed (${res.status})`);
        logger.error("api.request.failed", { path, status: res.status, requestId: reqId }, new Error(errMsg));
        const error = new Error(errMsg);
        (error as any).requestId = reqId;
        (error as any).status = res.status;
        (error as any).detail = errMsg;
        throw error;
      }

      return res.json();
    } catch (e: any) {
      if (!e.requestId && logger.getRequestId()) {
        e.requestId = logger.getRequestId();
      }
      throw e;
    }
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

    async getSession(sessionId: string) {
      return request<DebateSession>(`/api/sessions/${sessionId}`);
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
      const authHeaders = await getAuthHeaders();
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
        headers: {
          ...authHeaders,
        },
      });

      const reqId = res.headers.get("x-request-id");
      if (reqId) {
        logger.setRequestId(reqId);
      }

      if (!res.ok) {
        const errText = await res.text().catch(() => "");
        const errMsg = parseErrorDetail(errText, res.statusText || `Turn submission failed (${res.status})`);
        logger.error("api.turn_submission.failed", { sessionId: session.id, status: res.status, requestId: reqId }, new Error(errMsg));
        const error = new Error(errMsg);
        (error as any).requestId = reqId;
        (error as any).status = res.status;
        (error as any).detail = errMsg;
        throw error;
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
          logger.warn("event_stream.closed", { sessionId });
          es.close();
        };

        return () => es.close();
      } catch (err) {
        logger.error("event_stream.init_failed", { sessionId }, err);
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

    async getCoachHome() {
      return request<CoachHomeData>("/api/coach/home");
    },

    async getSessionCoachThread(sessionId: string) {
      return request<CoachThreadDetail>(`/api/coach/session/${sessionId}`);
    },

    async createGeneralCoachThread(text: string) {
      return request<CoachThreadDetail>("/api/coach/threads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
    },

    async getCoachThreadDetail(threadId: string) {
      return request<CoachThreadDetail>(`/api/coach/threads/${threadId}`);
    },

    async sendCoachTextMessage(threadId: string, text: string) {
      return request<CoachMessage>(`/api/coach/threads/${threadId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
    },

    async sendCoachAudioMessage(threadId: string, audio: Blob) {
      const authHeaders = await getAuthHeaders();
      const formData = new FormData();
      formData.append("audio", audio, "coach_audio.webm");

      const res = await fetch(`${apiBase}/api/coach/threads/${threadId}/audio`, {
        method: "POST",
        body: formData,
        credentials: "include",
        headers: {
          ...authHeaders,
        },
      });

      if (!res.ok) {
        const errText = await res.text().catch(() => "");
        throw new Error(parseErrorDetail(errText, "Failed to upload audio to coach"));
      }
      return res.json();
    },

    async correctCoachingMemory(correction) {
      return request("/api/coach/memory/correction", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(correction),
      });
    },

    getMediaAssetAudioUrl(assetId: string) {
      return `${apiBase}/api/media/${assetId}/audio`;
    },

    getClipAudioUrl(clipId: string) {
      return `${apiBase}/api/media/clips/${clipId}/audio`;
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
    async getSession(sessionId: string) {
      await delay(250);
      if (currentSession && currentSession.id === sessionId) {
        return currentSession;
      }
      return {
        id: sessionId,
        topic: "Social media has made friendships worse.",
        skillTarget: { id: "take_a_side", name: "Take a Side", hint: "Pick a side and hold it." },
        difficulty: "gentle",
        userSide: "agree",
        totalUserTurns: 3,
        currentTurn: 1,
        status: "active",
        turns: [],
        skillReminder: "Take a clear stance and defend it with reasons.",
      };
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
        opponentTurn: finished ? undefined : opponentTurn,
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
    async getCoachHome() {
      await delay(200);
      return {
        activeFocus: "Clarifying the core premise in turn 1",
        focusDetails: "Observed in 4 recent debates. Steady improvement.",
        progressSummary: mockProgressStats,
        presetQuestions: [
          { label: "Refutations", prompt: "How can I make my refutations punchier?" },
          { label: "Hesitation", prompt: "How do I cut down pauses before speaking?" },
          { label: "Concessions", prompt: "When should I concede without losing ground?" },
          { label: "Structure", prompt: "Give me a framework for 30-second spoken turns." },
        ],
        recentDebateThreads: [
          {
            id: "thread-mock-1",
            sessionId: "session-mock-1",
            threadType: "debate_review",
            title: "Debate Review · Social media friendships",
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            messageCount: 4,
            topic: "Social media has made friendships worse.",
            skillName: "Counterpoint",
          },
        ],
        generalThreads: [],
      };
    },
    async getSessionCoachThread(sessionId: string) {
      await delay(300);
      return {
        thread: {
          id: `thread-deb-${sessionId}`,
          sessionId,
          threadType: "debate_review",
          title: "Debate Coaching Session",
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          messageCount: 2,
          topic: "Social media has made friendships worse.",
          skillName: "Counterpoint",
        },
        messages: [
          {
            id: "msg-mock-1",
            threadId: `thread-deb-${sessionId}`,
            sender: "coach",
            messageType: "opening_analysis",
            text: "Strong performance challenging the core premise. Let's look at your timing in turn 2.",
            openingAnalysis: {
              overallAssessment: "You defended your position clearly with solid conviction.",
              mostImportantStrength: "You attacked the counterargument's definition of connection directly.",
              highestValueImprovement: "Lead with your main point immediately before elaborating.",
              suggestedQuickReplies: [
                { label: "How should I structure the opening?", prompt: "How should I structure the opening?" },
                { label: "Give me an example", prompt: "Give me an example of a sharper turn 2 refutation." },
                { label: "Let me retry turn 2", prompt: "I want to practice turn 2 again." },
              ],
            },
          },
        ],
      };
    },
    async createGeneralCoachThread(text: string) {
      await delay(300);
      const threadId = `thread-gen-${Date.now()}`;
      return {
        thread: {
          id: threadId,
          threadType: "general",
          title: text.slice(0, 40),
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          messageCount: 2,
        },
        messages: [
          {
            id: `msg-${Date.now()}-1`,
            threadId,
            sender: "user",
            messageType: "text",
            text,
          },
          {
            id: `msg-${Date.now()}-2`,
            threadId,
            sender: "coach",
            messageType: "text",
            text: "In spoken debates, leading with a crisp 1-sentence claim makes your response immediately memorable.",
            quickReplies: [
              { label: "Give me an example", prompt: "Give me an example." },
              { label: "Let me try that", prompt: "Let me practice that." },
            ],
          },
        ],
      };
    },
    async getCoachThreadDetail(threadId: string) {
      await delay(200);
      return {
        thread: {
          id: threadId,
          threadType: "general",
          title: "Coaching Thread",
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          messageCount: 2,
        },
        messages: [],
      };
    },
    async sendCoachTextMessage(threadId: string, text: string) {
      await delay(300);
      return {
        id: `msg-${Date.now()}`,
        threadId,
        sender: "coach",
        messageType: "text",
        text: `Regarding "${text}": Always isolate the opponent's unstated assumption first, then provide a single counter-example.`,
        quickReplies: [
          { label: "Try another example", prompt: "Give me another example." },
          { label: "How do I practice this?", prompt: "How do I practice this in a live debate?" },
        ],
      };
    },
    async sendCoachAudioMessage(threadId: string, _audio: Blob) {
      await delay(600);
      const userMsg: CoachMessage = {
        id: `msg-u-${Date.now()}`,
        threadId,
        sender: "user",
        messageType: "audio",
        text: "I practiced delivering the point with direct assertion.",
        durationSec: 4.2,
      };
      const coachMsg: CoachMessage = {
        id: `msg-c-${Date.now()}`,
        threadId,
        sender: "coach",
        messageType: "text",
        text: "Excellent pace. Your vocal attack on the opening premise was crisp and confident.",
        quickReplies: [
          { label: "Try another turn", prompt: "Let's try another turn." },
        ],
      };
      return { userMessage: userMsg, coachMessage: coachMsg };
    },
    async correctCoachingMemory() {
      await delay(200);
      return { success: true };
    },
    getMediaAssetAudioUrl(assetId: string) {
      return `/api/media/${assetId}/audio`;
    },
    getClipAudioUrl(clipId: string) {
      return `/api/media/clips/${clipId}/audio`;
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
const apiHost = process.env.NEXT_PUBLIC_API_URL ?? (typeof window !== "undefined" ? "" : "http://localhost:8000");

export const appService: AppService = isMock ? createMockService() : createHttpService(apiHost);
