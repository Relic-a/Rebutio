"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { TabBar } from "@/components/shared/TabBar";
import { appService } from "@/lib/api";
import { logger } from "@/lib/logger";
import { mockProgressStats } from "@/lib/mock/fixtures";
import type { CoachHomeData, QuickReply } from "@/lib/types";

const defaultCoachData: CoachHomeData = {
  activeFocus: "Isolating opponent assumptions directly",
  focusDetails: "Observed across your recent debates. Moving towards consistent mastery.",
  progressSummary: mockProgressStats,
  presetQuestions: [
    { label: "Refutations", prompt: "How can I make my refutations punchier?" },
    { label: "Hesitation", prompt: "How do I cut down pauses before speaking?" },
    { label: "Concessions", prompt: "When should I concede without losing ground?" },
    { label: "Structure", prompt: "Give me a framework for 30-second spoken turns." },
  ],
  recentDebateThreads: [],
  generalThreads: [],
};

let cachedCoachHome: CoachHomeData | null = null;

export default function CoachHomePage() {
  const router = useRouter();
  const [data, setData] = useState<CoachHomeData>(() => cachedCoachHome || defaultCoachData);
  const [loading, setLoading] = useState(false);
  const [customPrompt, setCustomPrompt] = useState("");
  const [isStarting, setIsStarting] = useState(false);
  const [correctionModalOpen, setCorrectionModalOpen] = useState(false);
  const [correctionText, setCorrectionText] = useState("");
  const [correctionSuccess, setCorrectionSuccess] = useState(false);

  useEffect(() => {
    appService
      .getCoachHome()
      .then((res) => {
        if (res) {
          cachedCoachHome = res;
          setData(res);
        }
      })
      .catch((err) => {
        logger.error("coach.home_load_failed", {}, err);
      });
  }, []);

  async function handleStartGeneralThread(promptText: string) {
    if (!promptText.trim() || isStarting) return;
    setIsStarting(true);
    try {
      const res = await appService.createGeneralCoachThread(promptText.trim());
      router.push(`/coach/thread/${res.thread.id}`);
    } catch (err) {
      logger.error("coach.general_thread_creation_failed", {}, err);
      setIsStarting(false);
    }
  }

  async function handleSaveCorrection() {
    if (!correctionText.trim()) return;
    try {
      await appService.correctCoachingMemory({
        patternType: "delivery_pattern",
        label: data?.activeFocus || "Active Focus",
        correctionText: correctionText.trim(),
        action: "update",
      });
      setCorrectionSuccess(true);
      setTimeout(() => {
        setCorrectionModalOpen(false);
        setCorrectionSuccess(false);
        setCorrectionText("");
      }, 1200);
    } catch (e) {
      logger.error("coach.memory_correction_failed", {}, e);
    }
  }

  return (
    <main className="mx-auto min-h-dvh w-full max-w-md bg-parchment px-5 py-6 pb-24 text-ink flex flex-col">
      {/* 1. Header */}
      <header className="mb-5">
        <span className="text-[10px] font-bold uppercase tracking-wider text-rally">Personal AI Coach</span>
        <h1 className="font-display text-2xl font-black tracking-tight text-ink">
          Coaching & Longitudinal Insights
        </h1>
        <p className="mt-1 text-xs text-ink-soft">
          Evidence-based guidance tailored to your spoken debate patterns.
        </p>
      </header>

      {loading ? (
        <div className="flex flex-1 items-center justify-center py-20 text-center text-ink-soft">
          <div className="w-8 h-8 border-2 border-rally border-t-transparent rounded-full animate-spin mb-3" />
          <p className="text-xs font-semibold">Loading your coaching dashboard...</p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* 2. Active Focus Card */}
          <section className="rounded-2xl bg-white p-4 border border-rally/20 shadow-sm">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-xs font-bold text-rally">
                <span className="w-2 h-2 rounded-full bg-rally animate-pulse" />
                <span>Active Focus Pattern</span>
              </div>
              <button
                onClick={() => setCorrectionModalOpen(true)}
                className="text-[11px] font-semibold text-ink-soft hover:text-rally underline"
              >
                Clarify note
              </button>
            </div>

            <h2 className="mt-2 text-sm font-bold text-ink">
              {data?.activeFocus || "Isolating opponent assumptions directly"}
            </h2>
            <p className="mt-1 text-xs text-ink-soft leading-relaxed">
              {data?.focusDetails || "Observed across your recent debates. Moving towards consistent mastery."}
            </p>
          </section>

          {/* 3. Quick-Start Question Presets */}
          <section>
            <h2 className="text-xs font-bold uppercase tracking-wider text-ink-soft mb-2.5">
              Practice & Strategy Prompts
            </h2>
            <div className="grid grid-cols-2 gap-2">
              {data?.presetQuestions.map((q, idx) => (
                <button
                  key={idx}
                  onClick={() => handleStartGeneralThread(q.prompt)}
                  disabled={isStarting}
                  className="rounded-2xl bg-white p-3 text-left border border-ink/5 shadow-sm hover:border-rally/40 hover:bg-rally-mist/30 transition-all text-xs font-medium text-ink flex flex-col justify-between"
                >
                  <span className="font-bold text-rally-deep text-[11px] mb-1">{q.label}</span>
                  <span className="text-ink-soft text-[11px] line-clamp-2">{q.prompt}</span>
                </button>
              ))}
            </div>
          </section>

          {/* 4. Start Custom Question */}
          <section className="rounded-2xl bg-white p-3.5 border border-ink/5 shadow-sm">
            <h2 className="text-xs font-bold text-ink mb-2">Ask Your Coach Anything</h2>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={customPrompt}
                onChange={(e) => setCustomPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    handleStartGeneralThread(customPrompt);
                  }
                }}
                placeholder="E.g. How do I counter emotional arguments?"
                className="flex-1 rounded-xl border border-ink/20 bg-parchment px-3 py-2 text-xs text-ink placeholder:text-ink-soft focus:border-rally focus:outline-none"
              />
              <button
                onClick={() => handleStartGeneralThread(customPrompt)}
                disabled={!customPrompt.trim() || isStarting}
                className="h-9 px-3.5 rounded-xl bg-rally text-white text-xs font-bold disabled:opacity-40 transition-opacity"
              >
                Ask
              </button>
            </div>
          </section>

          {/* 5. Recent Debate Coaching Threads */}
          <section>
            <h2 className="text-xs font-bold uppercase tracking-wider text-ink-soft mb-2.5">
              Recent Debate Coaching
            </h2>

            {data?.recentDebateThreads && data.recentDebateThreads.length > 0 ? (
              <div className="space-y-2">
                {data.recentDebateThreads.map((th) => (
                  <div
                    key={th.id}
                    onClick={() => router.push(`/coach/session/${th.sessionId || "latest"}`)}
                    className="cursor-pointer rounded-2xl bg-white p-3.5 border border-ink/5 shadow-sm hover:border-rally/30 transition-all flex items-center justify-between"
                  >
                    <div className="min-w-0 pr-3">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-bold text-coral bg-coral-soft/50 px-1.5 py-0.5 rounded">
                          {th.skillName || "Debate"}
                        </span>
                        <span className="text-[11px] text-ink-soft">{th.messageCount} messages</span>
                      </div>
                      <h3 className="text-xs font-bold text-ink truncate mt-1">{th.topic || th.title}</h3>
                    </div>

                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-ink-soft shrink-0">
                      <polyline points="9 18 15 12 9 6" />
                    </svg>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-2xl bg-white p-4 text-center text-xs text-ink-soft border border-ink/5">
                <p>Complete a live debate to see your audio clips and turn-by-turn coaching here.</p>
                <button
                  onClick={() => router.push("/path")}
                  className="mt-2 text-xs font-bold text-rally hover:underline"
                >
                  Start a debate →
                </button>
              </div>
            )}
          </section>
        </div>
      )}

      {/* Memory Correction Modal */}
      <AnimatePresence>
        {correctionModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4 backdrop-blur-sm">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-2xl border border-ink/10"
            >
              <h3 className="font-bold text-sm text-ink">Clarify Coaching Note</h3>
              <p className="mt-1 text-xs text-ink-soft">
                If the coach misinterpreted your style or intent, correct it here to guide future feedback.
              </p>

              <textarea
                value={correctionText}
                onChange={(e) => setCorrectionText(e.target.value)}
                placeholder="E.g. I paused to formulate a structured counterpoint, not because I was hesitant..."
                rows={3}
                className="mt-3 w-full rounded-xl border border-ink/20 bg-parchment p-3 text-xs text-ink placeholder:text-ink-soft focus:border-rally focus:outline-none"
              />

              {correctionSuccess && (
                <p className="mt-2 text-xs font-semibold text-rally">
                  Note updated! The coach will adapt future analyses.
                </p>
              )}

              <div className="mt-4 flex gap-2 justify-end">
                <button
                  onClick={() => setCorrectionModalOpen(false)}
                  className="rounded-xl px-3 py-1.5 text-xs font-semibold text-ink-soft hover:text-ink"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveCorrection}
                  disabled={!correctionText.trim()}
                  className="rounded-xl bg-rally px-4 py-1.5 text-xs font-bold text-white shadow hover:bg-rally/90 disabled:opacity-40"
                >
                  Save Correction
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      <TabBar />
    </main>
  );
}
