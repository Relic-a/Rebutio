"use client";

// Results: rewarding first, analytical second.
// 1) completion + XP + stars  2) debate outcome (never blocks progression)
// 3) coaching  4) full language feedback  5) continue.

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { Button } from "@/components/shared/Button";
import { StarRow } from "@/components/shared/StarRow";
import { appService } from "@/lib/api";
import { useStore } from "@/lib/state/store";
import type { DebateReview } from "@/lib/types";

export default function ResultsPage() {
  return (
    <Suspense fallback={null}>
      <Results />
    </Suspense>
  );
}

function Results() {
  const params = useSearchParams();
  const router = useRouter();
  const review = useStore((s) => s.lastReview);
  const firstSpar = params.get("first") === "1";
  const [showFeedback, setShowFeedback] = useState(false);
  const [disagreeOpen, setDisagreeOpen] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(false);

  if (!review) {
    return (
      <main className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="font-display text-xl font-bold">No debate results yet.</p>
        <Button onClick={() => router.replace("/home")}>Go home</Button>
      </main>
    );
  }

  const r: DebateReview = review;
  const outcomeLabel =
    r.outcome === "user_win" ? "You won" : r.outcome === "opponent_win" ? "Rebutio won" : r.outcome === "draw" ? "Draw" : "Undetermined";
  const outcomeTone =
    r.outcome === "user_win" ? "bg-amber-soft text-amber-900" : r.outcome === "opponent_win" ? "bg-coral-soft text-coral" : "bg-rally-mist text-rally-deep";

  return (
    <main className="mx-auto min-h-dvh w-full max-w-md px-6 py-10">
      {/* 1 — completion */}
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="text-center">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">{firstSpar ? "First spar complete" : "Spar complete"}</p>
        <h1 className="mt-1 font-display text-3xl font-extrabold tracking-tight">{firstSpar ? "You came in strong." : "Debate done."}</h1>
        <div className="mt-4 flex items-center justify-center gap-4 text-sm font-semibold">
          <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }} className="rounded-full bg-rally-mist px-4 py-1.5 text-rally-deep">
            +{r.xpEarned} XP
          </motion.span>
          {r.streakExtended && (
            <motion.span initial={{ scale: 0.7, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ delay: 0.5, type: "spring" }} className="rounded-full bg-amber-soft px-4 py-1.5 text-amber-900">
              🔥 Streak extended
            </motion.span>
          )}
        </div>

        {/* stars reveal individually */}
        <motion.div className="mt-6 flex justify-center" initial="hidden" animate="show" variants={{ show: { transition: { staggerChildren: 0.35, delayChildren: 0.7 } } }}>
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              variants={{ hidden: { scale: 0, opacity: 0, rotate: -40 }, show: { scale: 1, opacity: 1, rotate: 0 } }}
              transition={{ type: "spring", stiffness: 280, damping: 14 }}
              className={`text-5xl ${i < r.stars.stars ? "text-amber" : "text-ink/15"}`}
              role="img"
              aria-label={i < r.stars.stars ? `Star ${i + 1} earned` : `Star ${i + 1} not earned`}
            >
              ★
            </motion.span>
          ))}
        </motion.div>
        <ul className="mx-auto mt-4 max-w-xs space-y-1 text-sm text-ink-soft">
          <li className={r.stars.completed ? "font-medium text-ink" : ""}>✓ Completed</li>
          <li className={r.stars.skillDemonstrated ? "font-medium text-ink" : ""}>{r.stars.skillDemonstrated ? "✓" : "○"} Skill demonstrated</li>
          <li className={r.stars.stars === 3 ? "font-medium text-ink" : ""}>{r.stars.stars === 3 ? "✓ Mastery shown" : "○ Mastery still developing"}</li>
        </ul>
        {r.stars.masteryNote && <p className="mx-auto mt-3 max-w-xs text-sm text-ink-soft">{r.stars.masteryNote}</p>}
      </motion.div>

      {/* 2 — debate outcome (separate, never blocks progression) */}
      <motion.section initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }} className="mt-10">
        <div className="flex items-center justify-between">
          <span className={`rounded-full px-5 py-2 font-display text-lg font-bold ${outcomeTone}`}>{outcomeLabel}</span>
          <button onClick={() => setDisagreeOpen((o) => !o)} className="text-sm font-medium text-ink-soft underline underline-offset-4">
            Disagree with this result?
          </button>
        </div>
        <AnimatePresence>
          {disagreeOpen && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
              <div className="mt-3 rounded-2xl bg-white p-4 text-sm text-ink-soft shadow-[0_4px_18px_rgba(34,39,31,0.06)]">
                <p>That&apos;s okay — debate judging can be subjective. Your learning progress isn&apos;t affected.</p>
                {feedbackSent ? (
                  <p className="mt-2 font-medium text-ink">Thanks — noted.</p>
                ) : (
                  <button
                    onClick={async () => {
                      await appService.submitReviewFeedback({ sessionId: "current", verdict: "disagree" }).catch(() => {});
                      setFeedbackSent(true);
                    }}
                    className="mt-2 font-semibold text-rally underline underline-offset-4"
                  >
                    Send feedback on this call
                  </button>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        {r.argumentFeedback?.insight && <p className="mt-4 text-sm leading-relaxed text-ink-soft">{r.argumentFeedback.insight}</p>}
      </motion.section>

      {/* 3 — main coaching */}
      {r.argumentFeedback && (
        <motion.section initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.55 }} className="mt-10 space-y-4">
          <h2 className="font-display text-xl font-bold">After your debate</h2>
          <div className="rounded-2xl bg-white p-4 shadow-[0_4px_18px_rgba(34,39,31,0.06)]">
            <p className="text-xs font-semibold uppercase tracking-wider text-rally">Strong</p>
            <p className="mt-1 text-sm">{r.argumentFeedback.strength}</p>
          </div>
          <div className="rounded-2xl bg-white p-4 shadow-[0_4px_18px_rgba(34,39,31,0.06)]">
            <p className="text-xs font-semibold uppercase tracking-wider text-coral">Work on</p>
            <p className="mt-1 text-sm">{r.argumentFeedback.improvement}</p>
          </div>
        </motion.section>
      )}

      {/* 4 — full language feedback */}
      {r.languageFeedback && (
        <motion.section initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.65 }} className="mt-8">
          {!showFeedback ? (
            <button onClick={() => setShowFeedback(true)} className="w-full rounded-full border-2 border-ink/15 bg-white py-3.5 font-semibold">
              See full feedback
            </button>
          ) : (
            <div className="space-y-4">
              <h2 className="font-display text-xl font-bold">Language feedback</h2>
              {r.languageFeedback.pronunciation && r.languageFeedback.pronunciation.length > 0 && (
                <div className="rounded-2xl bg-white p-4 shadow-[0_4px_18px_rgba(34,39,31,0.06)]">
                  <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Pronunciation</p>
                  {r.languageFeedback.pronunciation.map((p, i) => (
                    <div key={i} className="mt-3 border-t border-ink/5 pt-3 first:border-0 first:pt-0">
                      <p className="font-display font-bold">
                        &ldquo;{p.sound}&rdquo; sound {p.occurrences ? <span className="text-ink-soft">· {p.occurrences}× </span> : null}
                      </p>
                      {p.heardIn && <p className="mt-0.5 text-sm text-ink-soft">Heard in: {p.heardIn.join(", ")}</p>}
                      <p className="mt-1 text-sm">{p.note}</p>
                    </div>
                  ))}
                  <p className="mt-3 text-xs text-ink-soft">Clarity and intelligibility are what matter — accent isn&apos;t a defect.</p>
                </div>
              )}
              {r.languageFeedback.fluency && (
                <DetailBlock label="Fluency" summary={r.languageFeedback.fluency.summary} score={r.languageFeedback.fluency.score} trend={r.languageFeedback.fluency.trend} />
              )}
              {r.languageFeedback.grammar && (
                <DetailBlock label="Grammar" summary={r.languageFeedback.grammar.summary} examples={r.languageFeedback.grammar.examples} />
              )}
              {r.languageFeedback.vocabulary && (
                <DetailBlock label="Vocabulary" summary={r.languageFeedback.vocabulary.summary} examples={r.languageFeedback.vocabulary.examples} />
              )}
              {r.languageFeedback.clarity && (
                <DetailBlock label="Clarity" summary={r.languageFeedback.clarity.summary} score={r.languageFeedback.clarity.score} />
              )}
            </div>
          )}
        </motion.section>
      )}

      {/* 5 — continue */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.75 }} className="mt-10 flex flex-col gap-3 pb-8">
        <Button onClick={() => router.replace("/home")} className="w-full">
          Next Debate
        </Button>
        {showFeedback && (
          <Button variant="secondary" onClick={() => router.replace("/progress")} className="w-full">
            Review feedback in Progress
          </Button>
        )}
        {r.stars.stars < 3 && (
          <p className="text-center text-xs text-ink-soft">You can replay this topic later for more stars — or leave it. Skills return in future debates.</p>
        )}
      </motion.div>
    </main>
  );
}

function DetailBlock({ label, summary, score, trend, examples }: { label: string; summary: string; score?: number; trend?: string; examples?: string[] }) {
  return (
    <div className="rounded-2xl bg-white p-4 shadow-[0_4px_18px_rgba(34,39,31,0.06)]">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">{label}</p>
        {score !== undefined && <p className="text-sm font-semibold text-rally">{score}/100</p>}
        {trend && <p className="text-xs font-medium text-amber-900 capitalize">{trend}</p>}
      </div>
      <p className="mt-1 text-sm">{summary}</p>
      {examples && examples.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm text-ink-soft">
          {examples.map((e) => (
            <li key={e}>· {e}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
