"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { Button } from "@/components/shared/Button";
import { appService } from "@/lib/api";
import { useStore } from "@/lib/state/store";
import type { DebateReview } from "@/lib/types";

export default function ResultsPage() {
  return (
    <Suspense fallback={<div className="min-h-dvh flex items-center justify-center text-ink-soft">Loading results...</div>}>
      <Results />
    </Suspense>
  );
}

function Results() {
  const params = useSearchParams();
  const router = useRouter();
  const review = useStore((s) => s.lastReview);
  const [showTranscript, setShowTranscript] = useState(false);
  const [disagreeOpen, setDisagreeOpen] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(false);
  const [transcriptTurns, setTranscriptTurns] = useState<{ speaker: string; text: string }[] | null>(null);
  const [loadingTranscript, setLoadingTranscript] = useState(false);

  const sessionId = review?.sessionId || "latest";

  useEffect(() => {
    if (showTranscript && !transcriptTurns) {
      setLoadingTranscript(true);
      appService.getSessionCoachThread(sessionId)
        .then((detail) => {
          if (detail.debateSession?.turns && detail.debateSession.turns.length > 0) {
            setTranscriptTurns(
              detail.debateSession.turns.map((t) => ({
                speaker: t.speaker,
                text: t.text || "",
              }))
            );
          } else {
            setTranscriptTurns([]);
          }
        })
        .catch(() => setTranscriptTurns([]))
        .finally(() => setLoadingTranscript(false));
    }
  }, [showTranscript, sessionId, transcriptTurns]);

  if (!review) {
    return (
      <main className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center bg-parchment text-ink">
        <p className="font-display text-xl font-bold">No debate results yet.</p>
        <Button onClick={() => router.replace("/home")}>Go Home</Button>
      </main>
    );
  }

  const r: DebateReview = review;

  const outcomeLabel =
    r.outcome === "user_win" ? "You Won" : r.outcome === "opponent_win" ? "Rebutio Won" : r.outcome === "draw" ? "Draw" : "Debate Concluded";
  const outcomeColor =
    r.outcome === "user_win" ? "bg-amber-soft text-amber-900 border-amber/30" : r.outcome === "opponent_win" ? "bg-coral-soft text-coral border-coral/30" : "bg-rally-mist text-rally-deep border-rally/30";

  // 4 Integer Scores
  const scoreTechnique = r.scoreTechnique?.score ?? 0;
  const rubricTechnique = r.scoreTechnique?.rubric ?? r.argumentFeedback?.strength ?? "Directly challenged the opponent's core premise.";

  const scoreGrammar = r.scoreGrammar?.score ?? 0;
  const rubricGrammar = r.scoreGrammar?.rubric ?? r.languageFeedback?.grammar?.summary ?? "Clean grammatical structures under live pressure.";

  const scoreVocabulary = r.scoreVocabulary?.score ?? 0;
  const rubricVocabulary = r.scoreVocabulary?.rubric ?? r.languageFeedback?.vocabulary?.summary ?? "Persuasive and topic-appropriate terminology.";

  const scoreDelivery = r.scoreDelivery?.score ?? 0;
  const rubricDelivery = r.scoreDelivery?.rubric ?? r.languageFeedback?.fluency?.summary ?? "Confident delivery with steady pace.";

  const strongestMoment = r.strongestMoment || r.argumentFeedback?.strength || "You directly challenged their central premise.";
  const improvementOpportunity = r.improvementOpportunity || r.argumentFeedback?.improvement || "Lead with your main point immediately in your first sentence.";

  return (
    <main className="mx-auto min-h-dvh w-full max-w-md px-5 py-8 bg-parchment text-ink flex flex-col pb-16">
      {/* 1. Header & Outcome */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="text-center">
        <span className={`inline-block rounded-full border px-4 py-1 text-xs font-bold uppercase tracking-wider ${outcomeColor}`}>
          {outcomeLabel}
        </span>

        <h1 className="mt-3 font-display text-2xl font-black tracking-tight text-ink">
          Debate Summary
        </h1>
        <p className="mt-1 text-xs text-ink-soft max-w-xs mx-auto truncate font-medium">
          {r.topic}
        </p>

        {/* Badges */}
        <div className="mt-3 flex items-center justify-center gap-3 text-xs font-bold">
          <span className="rounded-full bg-rally-mist px-3 py-1 text-rally-deep">
            +{r.xpEarned || 120} XP
          </span>
          {r.streakExtended && (
            <span className="rounded-full bg-amber-soft px-3 py-1 text-amber-900">
              🔥 Streak Maintained
            </span>
          )}
        </div>
      </motion.div>

      {/* 2. 4 Integer Scores out of 10 */}
      <motion.section
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="mt-6 space-y-3"
      >
        <h2 className="text-xs font-bold uppercase tracking-wider text-ink-soft">
          Performance Scores
        </h2>

        <div className="grid grid-cols-2 gap-2.5">
          {/* Technique */}
          <div className="rounded-2xl bg-white p-3.5 border border-ink/5 shadow-sm">
            <div className="flex items-baseline justify-between">
              <span className="text-xs font-bold text-ink">Technique</span>
              <span className="font-mono text-lg font-black text-rally">
                {scoreTechnique > 0 ? scoreTechnique : "—"}{scoreTechnique > 0 && <span className="text-xs text-ink-soft">/10</span>}
              </span>
            </div>
            <p className="mt-1.5 text-[11px] text-ink-soft leading-tight line-clamp-2">{rubricTechnique}</p>
          </div>

          {/* Grammar */}
          <div className="rounded-2xl bg-white p-3.5 border border-ink/5 shadow-sm">
            <div className="flex items-baseline justify-between">
              <span className="text-xs font-bold text-ink">Grammar</span>
              <span className="font-mono text-lg font-black text-rally">
                {scoreGrammar > 0 ? scoreGrammar : "—"}{scoreGrammar > 0 && <span className="text-xs text-ink-soft">/10</span>}
              </span>
            </div>
            <p className="mt-1.5 text-[11px] text-ink-soft leading-tight line-clamp-2">{rubricGrammar}</p>
          </div>

          {/* Vocabulary */}
          <div className="rounded-2xl bg-white p-3.5 border border-ink/5 shadow-sm">
            <div className="flex items-baseline justify-between">
              <span className="text-xs font-bold text-ink">Vocabulary</span>
              <span className="font-mono text-lg font-black text-rally">
                {scoreVocabulary > 0 ? scoreVocabulary : "—"}{scoreVocabulary > 0 && <span className="text-xs text-ink-soft">/10</span>}
              </span>
            </div>
            <p className="mt-1.5 text-[11px] text-ink-soft leading-tight line-clamp-2">{rubricVocabulary}</p>
          </div>

          {/* Delivery */}
          <div className="rounded-2xl bg-white p-3.5 border border-ink/5 shadow-sm">
            <div className="flex items-baseline justify-between">
              <span className="text-xs font-bold text-ink">Delivery</span>
              <span className="font-mono text-lg font-black text-rally">
                {scoreDelivery > 0 ? scoreDelivery : "—"}{scoreDelivery > 0 && <span className="text-xs text-ink-soft">/10</span>}
              </span>
            </div>
            <p className="mt-1.5 text-[11px] text-ink-soft leading-tight line-clamp-2">{rubricDelivery}</p>
          </div>
        </div>
      </motion.section>

      {/* 3. Standout Moments (1 Strongest + 1 Improvement) */}
      <motion.section
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25 }}
        className="mt-5 space-y-2.5"
      >
        <div className="rounded-2xl bg-rally-mist/60 border border-rally/15 p-3.5">
          <div className="flex items-center gap-1.5 text-xs font-bold text-rally-deep">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            <span>Strongest Moment</span>
          </div>
          <p className="mt-1.5 text-xs font-medium text-ink leading-relaxed">
            {strongestMoment}
          </p>
        </div>

        <div className="rounded-2xl bg-amber-soft/60 border border-amber/20 p-3.5">
          <div className="flex items-center gap-1.5 text-xs font-bold text-amber-900">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>Primary Focus for Next Time</span>
          </div>
          <p className="mt-1.5 text-xs font-medium text-ink leading-relaxed">
            {improvementOpportunity}
          </p>
        </div>
      </motion.section>

      {/* 4. Primary CTA: Review with Coach */}
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.35 }}
        className="mt-8 space-y-3"
      >
        <button
          onClick={() => router.push(`/coach/session/${sessionId}`)}
          className="w-full rounded-2xl bg-rally py-4 text-center text-sm font-bold text-white shadow-lg hover:bg-rally/90 active:scale-[0.99] transition-all flex items-center justify-center gap-2"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z" />
          </svg>
          <span>Review with my coach</span>
        </button>

        {/* Secondary Actions */}
        <div className="flex gap-2">
          <button
            onClick={() => setShowTranscript((s) => !s)}
            className="flex-1 rounded-xl border border-ink/10 bg-white py-2.5 text-xs font-bold text-ink hover:bg-parchment transition-colors"
          >
            {showTranscript ? "Hide Transcript" : "View Transcript"}
          </button>

          <button
            onClick={() => router.push("/path")}
            className="flex-1 rounded-xl border border-ink/10 bg-white py-2.5 text-xs font-bold text-ink hover:bg-parchment transition-colors"
          >
            Next Debate
          </button>
        </div>
      </motion.div>

      {/* 5. Expandable Real Transcript Drawer */}
      <AnimatePresence>
        {showTranscript && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-4 overflow-hidden rounded-2xl bg-white p-4 border border-ink/10 text-xs shadow-inner"
          >
            <h3 className="font-bold text-ink mb-3 uppercase tracking-wider text-[10px]">Debate Transcript</h3>
            {loadingTranscript ? (
              <p className="text-ink-soft italic">Loading debate transcript...</p>
            ) : transcriptTurns && transcriptTurns.length > 0 ? (
              <div className="space-y-2.5 max-h-80 overflow-y-auto pr-1">
                {transcriptTurns.map((turn, i) => (
                  <div
                    key={i}
                    className={`rounded-xl p-3 ${
                      turn.speaker === "user"
                        ? "bg-rally-mist/60 border border-rally/15 text-ink"
                        : "bg-parchment border border-ink/10 text-ink"
                    }`}
                  >
                    <span className="font-bold text-[10px] uppercase tracking-wider text-ink-soft block mb-1">
                      {turn.speaker === "user" ? "You" : "Rebutio"}
                    </span>
                    <p className="text-xs leading-relaxed whitespace-pre-wrap">{turn.text}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-ink-soft italic">No turn transcripts recorded for this session.</p>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Disagree feedback toggle */}
      <div className="mt-8 text-center">
        <button
          onClick={() => setDisagreeOpen((o) => !o)}
          className="text-[11px] font-semibold text-ink-soft hover:underline"
        >
          Disagree with this adjudication?
        </button>

        {disagreeOpen && (
          <div className="mt-2 rounded-xl bg-white p-3 text-xs text-ink-soft border border-ink/10">
            {feedbackSent ? (
              <p className="text-rally font-semibold">Feedback recorded for coach tuning.</p>
            ) : (
              <button
                onClick={async () => {
                  await appService.submitReviewFeedback({ sessionId, verdict: "disagree" }).catch(() => {});
                  setFeedbackSent(true);
                }}
                className="font-bold text-rally underline"
              >
                Submit adjudication feedback
              </button>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
