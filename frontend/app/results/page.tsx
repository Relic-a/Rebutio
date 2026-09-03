"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { Button } from "@/components/shared/Button";
import { appService } from "@/lib/api";
import { useStore } from "@/lib/state/store";
import type { DebateReview } from "@/lib/types";
import { PronunciationText } from "@/components/coach/PronunciationText";

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
  const storedTranscriptTurns = useStore((s) => s.lastTranscriptTurns);
  const [showTranscript, setShowTranscript] = useState(false);
  const [disagreeOpen, setDisagreeOpen] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(false);
  const [transcriptTurns, setTranscriptTurns] = useState<{ speaker: string; text: string }[] | null>(
    () => storedTranscriptTurns || null
  );
  const [loadingTranscript, setLoadingTranscript] = useState(false);

  const sessionId = review?.sessionId || "latest";

  useEffect(() => {
    if (storedTranscriptTurns && !transcriptTurns) {
      setTranscriptTurns(storedTranscriptTurns);
    }
  }, [storedTranscriptTurns, transcriptTurns]);

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
    r.outcome === "user_win"
      ? "You Won"
      : r.outcome === "opponent_win"
      ? "Rebutio Won"
      : r.outcome === "draw"
      ? "Draw"
      : "Undetermined";
  const outcomeColor =
    r.outcome === "user_win"
      ? "bg-amber-soft text-amber-900 border-amber/30"
      : r.outcome === "opponent_win"
      ? "bg-coral-soft text-coral border-coral/30"
      : r.outcome === "draw"
      ? "bg-rally-mist text-rally-deep border-rally/30"
      : "bg-ink/5 text-ink-soft border-ink/15";

  // Spoken-language scores
  const scoreClarity = r.languageFeedback?.clarity?.score ?? null;
  const rubricClarity = r.languageFeedback?.clarity?.summary ?? "How easily a listener could follow your spoken ideas.";

  const scoreGrammar = r.scoreGrammar?.score ?? null;
  const rubricGrammar = r.scoreGrammar?.rubric ?? r.languageFeedback?.grammar?.summary ?? "Insufficient speech sample to evaluate grammar.";

  const scoreVocabulary = r.scoreVocabulary?.score ?? null;
  const rubricVocabulary = r.scoreVocabulary?.rubric ?? r.languageFeedback?.vocabulary?.summary ?? "Insufficient vocabulary sample to evaluate.";

  const scoreDelivery = r.scoreDelivery?.score ?? null;
  const rubricDelivery = r.scoreDelivery?.rubric ?? r.languageFeedback?.fluency?.summary ?? "Insufficient audio recording length to evaluate delivery.";

  const pronunciationFindings = r.languageFeedback?.pronunciation ?? [];
  const strongestMoment = r.strongestMoment || r.languageFeedback?.clarity?.summary || r.languageFeedback?.grammar?.summary || r.languageFeedback?.vocabulary?.summary || "Your speech stayed understandable through the exchange.";
  const improvementOpportunity = r.improvementOpportunity || pronunciationFindings[0]?.note || r.languageFeedback?.fluency?.summary || r.languageFeedback?.grammar?.summary || "Keep your next answer short and easy to say aloud.";
  const grammarAdvice = r.grammarAdvice;
  const vocabularyAdvice = r.vocabularyAdvice;
  const pronunciationAdvice = r.pronunciationAdvice;

  return (
    <main className="mx-auto min-h-dvh w-full max-w-md px-4 py-6 text-ink flex flex-col pb-16">
      {/* 1. Header & Outcome */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ type: "spring", stiffness: 260, damping: 26 }}>
        <div className="card-shell-dark">
          <div className="card-core arena-panel relative overflow-hidden p-6 text-center text-white">
            <div className="pointer-events-none absolute -left-12 -top-12 h-44 w-44 rounded-full bg-amber/25 blur-3xl" aria-hidden />
            <div className="pointer-events-none absolute -bottom-14 -right-10 h-44 w-44 rounded-full bg-rally/40 blur-3xl" aria-hidden />
            <span className={`relative inline-block rounded-full px-4 py-1.5 text-[11px] font-black uppercase tracking-[0.16em] ring-1 ${outcomeColor} shadow-sm`}>
              {outcomeLabel}
            </span>

            <h1 className="relative mt-3 font-display text-[1.9rem] font-black tracking-tight">
              Speaking review
            </h1>
            <p className="relative mx-auto mt-1 max-w-xs truncate text-[13px] font-medium text-white/70">
              {r.topic}
            </p>

            {/* Badges */}
            <div className="relative mt-4 flex items-center justify-center gap-2 text-xs font-black tabular-nums">
              {r.xpEarned > 0 ? (
                <span className="rounded-full bg-[#ffe9bd] px-3.5 py-1.5 text-ink shadow">
                  +{r.xpEarned} XP
                </span>
              ) : (
                <span className="rounded-full bg-white/12 px-3.5 py-1.5 text-white/80 ring-1 ring-white/20">
                  Session recorded
                </span>
              )}
              {r.streakExtended && (
                <span className="rounded-full bg-white/12 px-3.5 py-1.5 text-amber-200 ring-1 ring-white/20">
                  Streak kept
                </span>
              )}
            </div>
          </div>
        </div>
      </motion.div>

      {/* 2. Spoken-language scores */}
      <motion.section
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="mt-6 space-y-3"
      >
        <h2 className="text-xs font-bold uppercase tracking-wider text-ink-soft">
          Spoken English
        </h2>

        <div className="grid grid-cols-2 gap-2.5">
          {/* Clarity */}
          <div className="card-paper rounded-[1.3rem] p-3.5 transition-transform duration-300 hover:-translate-y-0.5">
            <div className="flex items-baseline justify-between">
              <span className="text-xs font-bold text-ink">Clarity</span>
              <span className="font-mono text-lg font-black text-rally">
                {scoreClarity !== null && scoreClarity > 0 ? (
                  <>
                    {scoreClarity}
                    <span className="text-xs text-ink-soft">/10</span>
                  </>
                ) : (
                  <span className="text-ink-soft text-base font-medium">—</span>
                )}
              </span>
            </div>
            <p className="mt-1.5 text-[11px] text-ink-soft leading-tight line-clamp-2">{rubricClarity}</p>
          </div>

          {/* Grammar */}
          <div className="card-paper rounded-[1.3rem] p-3.5 transition-transform duration-300 hover:-translate-y-0.5">
            <div className="flex items-baseline justify-between">
              <span className="text-xs font-bold text-ink">Grammar</span>
              <span className="font-mono text-lg font-black text-rally">
                {scoreGrammar !== null && scoreGrammar > 0 ? (
                  <>
                    {scoreGrammar}
                    <span className="text-xs text-ink-soft">/10</span>
                  </>
                ) : (
                  <span className="text-ink-soft text-base font-medium">—</span>
                )}
              </span>
            </div>
            <p className="mt-1.5 text-[11px] text-ink-soft leading-tight line-clamp-2">{rubricGrammar}</p>
          </div>

          {/* Vocabulary */}
          <div className="card-paper rounded-[1.3rem] p-3.5 transition-transform duration-300 hover:-translate-y-0.5">
            <div className="flex items-baseline justify-between">
              <span className="text-xs font-bold text-ink">Vocabulary</span>
              <span className="font-mono text-lg font-black text-rally">
                {scoreVocabulary !== null && scoreVocabulary > 0 ? (
                  <>
                    {scoreVocabulary}
                    <span className="text-xs text-ink-soft">/10</span>
                  </>
                ) : (
                  <span className="text-ink-soft text-base font-medium">—</span>
                )}
              </span>
            </div>
            <p className="mt-1.5 text-[11px] text-ink-soft leading-tight line-clamp-2">{rubricVocabulary}</p>
          </div>

          {/* Delivery */}
          <div className="card-paper rounded-[1.3rem] p-3.5 transition-transform duration-300 hover:-translate-y-0.5">
            <div className="flex items-baseline justify-between">
              <span className="text-xs font-bold text-ink">Delivery</span>
              <span className="font-mono text-lg font-black text-rally">
                {scoreDelivery !== null && scoreDelivery > 0 ? (
                  <>
                    {scoreDelivery}
                    <span className="text-xs text-ink-soft">/10</span>
                  </>
                ) : (
                  <span className="text-ink-soft text-base font-medium">—</span>
                )}
              </span>
            </div>
            <p className="mt-1.5 text-[11px] text-ink-soft leading-tight line-clamp-2">{rubricDelivery}</p>
          </div>
        </div>
      </motion.section>

      {pronunciationFindings.length > 0 && (
        <motion.section
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.22 }}
          className="mt-5 rounded-2xl border border-rally/20 bg-white p-4 shadow-sm"
        >
          <h2 className="text-xs font-bold uppercase tracking-wider text-rally-deep">Pronunciation to practice</h2>
          <div className="mt-3 space-y-3">
            {pronunciationFindings.slice(0, 4).map((finding, index) => {
              const practiceWord = finding.heardIn?.[0] || finding.sound;
              return (
                <div key={index} className="rounded-xl bg-rally-mist/50 p-3">
                  <PronunciationText
                    text={`[[pronounce:${practiceWord}]]`}
                    className="text-sm font-bold text-rally-deep"
                  />
                  <p className="mt-1 text-xs leading-relaxed text-ink-soft">{finding.note}</p>
                </div>
              );
            })}
          </div>
          <p className="mt-3 text-xs text-ink-soft">Open Coach, listen to each word, then send a voice attempt for fresh phoneme feedback.</p>
        </motion.section>
      )}

      {/* 3. Language highlights */}
      <motion.section
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25 }}
        className="mt-5 space-y-2.5"
      >
        {strongestMoment && (
          <div className="rounded-2xl bg-rally-mist/60 border border-rally/15 p-3.5">
            <div className="flex items-center gap-1.5 text-xs font-bold text-rally-deep">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              <span>What Worked in Your Speech</span>
            </div>
            <p className="mt-1.5 text-xs font-medium text-ink leading-relaxed">
              <PronunciationText text={strongestMoment} className="whitespace-pre-wrap" />
            </p>
          </div>
        )}

        <div className="rounded-2xl bg-amber-soft/60 border border-amber/20 p-3.5">
          <div className="flex items-center gap-1.5 text-xs font-bold text-amber-900">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>Primary Language Focus</span>
          </div>
          <p className="mt-1.5 text-xs font-medium text-ink leading-relaxed">
            <PronunciationText text={improvementOpportunity} className="whitespace-pre-wrap" />
          </p>
        </div>

        {grammarAdvice && (
          <div className="rounded-2xl bg-purple-50/70 border border-purple-200/40 p-3.5">
            <div className="flex items-center gap-1.5 text-xs font-bold text-purple-900">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              </svg>
              <span>Grammar & Syntax</span>
            </div>
            <p className="mt-1.5 text-xs font-medium text-ink leading-relaxed">
              <PronunciationText text={grammarAdvice} className="whitespace-pre-wrap" />
            </p>
          </div>
        )}

        {vocabularyAdvice && (
          <div className="rounded-2xl bg-sky-50/70 border border-sky-200/40 p-3.5">
            <div className="flex items-center gap-1.5 text-xs font-bold text-sky-900">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="16" x2="12" y2="12" />
                <line x1="12" y1="8" x2="12.01" y2="8" />
              </svg>
              <span>Vocabulary & Collocations</span>
            </div>
            <p className="mt-1.5 text-xs font-medium text-ink leading-relaxed">
              <PronunciationText text={vocabularyAdvice} className="whitespace-pre-wrap" />
            </p>
          </div>
        )}

        {pronunciationAdvice && (
          <div className="rounded-2xl bg-amber-50/70 border border-amber-200/40 p-3.5">
            <div className="flex items-center gap-1.5 text-xs font-bold text-amber-900">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
              <span>Pronunciation & Acoustics</span>
            </div>
            <p className="mt-1.5 text-xs font-medium text-ink leading-relaxed">
              <PronunciationText text={pronunciationAdvice} className="whitespace-pre-wrap" />
            </p>
          </div>
        )}
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
          <span>Practice with my language coach</span>
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
          Disagree with this review?
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
