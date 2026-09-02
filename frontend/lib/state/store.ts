"use client";

// Local demo state. Persists to localStorage so refreshing
// doesn't reset onboarding / progression. All mock data.

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { DebateReview, OnboardingPreferences } from "@/lib/types";
import { defaultPreferences } from "@/lib/mock/fixtures";

type StoreState = {
  onboarded: boolean;
  preferences: OnboardingPreferences;
  xp: number;
  streakDays: number;
  streakExtendedThisSession: boolean;
  starsByNodeId: Record<string, 0 | 1 | 2 | 3>;
  record: { wins: number; losses: number; draws: number };
  debatesCompleted: number;
  lastReview: DebateReview | null;
  lastTranscriptTurns: Array<{ speaker: string; text: string }> | null;
  completeOnboarding: (prefs: OnboardingPreferences) => void;
  applyReview: (review: DebateReview, opts?: { recordStars?: boolean; turns?: Array<{ speaker: string; text: string }> }) => void;
  reset: () => void;
};

export const useStore = create<StoreState>()(
  persist(
    (set, get) => ({
      onboarded: false,
      preferences: defaultPreferences,
      xp: 0,
      streakDays: 1,
      streakExtendedThisSession: false,
      starsByNodeId: {},
      record: { wins: 0, losses: 0, draws: 0 },
      debatesCompleted: 0,
      lastReview: null,
      lastTranscriptTurns: null,
      completeOnboarding: (prefs) => set({ onboarded: true, preferences: prefs }),
      applyReview: (review, opts) => {
        const cur = get();
        const targetSkill = review.skillAssessment?.targetSkill;
        const starsByNodeId = { ...cur.starsByNodeId };
        if (opts?.recordStars !== false && targetSkill) {
          const prev = starsByNodeId[targetSkill] ?? 0;
          starsByNodeId[targetSkill] = Math.max(prev, review.stars.stars) as 0 | 1 | 2 | 3;
        }
        set({
          xp: cur.xp + review.xpEarned,
          streakDays: review.streakExtended ? cur.streakDays + 1 : cur.streakDays,
          streakExtendedThisSession: review.streakExtended,
          debatesCompleted: cur.debatesCompleted + 1,
          record: {
            wins: cur.record.wins + (review.outcome === "user_win" ? 1 : 0),
            losses: cur.record.losses + (review.outcome === "opponent_win" ? 1 : 0),
            draws: cur.record.draws + (review.outcome === "draw" ? 1 : 0),
          },
          lastReview: review,
          lastTranscriptTurns: opts?.turns ?? cur.lastTranscriptTurns,
          starsByNodeId,
        });
      },
      reset: () =>
        set({
          onboarded: false,
          preferences: defaultPreferences,
          xp: 0,
          streakDays: 1,
          streakExtendedThisSession: false,
          starsByNodeId: {},
          record: { wins: 0, losses: 0, draws: 0 },
          debatesCompleted: 0,
          lastReview: null,
        }),
    }),
    { name: "rebutio-demo" }
  )
);
