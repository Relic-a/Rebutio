"use client";

// Live debate experience. Renders the session it is given; knows nothing
// about backends, providers, or transports. Deals in semantic states only.

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { appService, noteCurrentSession } from "@/lib/api";
import { capture } from "@/lib/media/capture";
import { logger } from "@/lib/logger";
import type { DebateReview, DebateSession, DebateSetup } from "@/lib/types";

type Phase =
  | "turn" // user's turn, mic ready
  | "recording"
  | "reviewing-clip" // user re-listens before sending
  | "submitted"
  | "thinking"
  | "opponent" // opponent response displayed
  | "finished"
  | "reviewing";

export function DebateFlow({
  session,
  setup,
  onFinish,
}: {
  session: DebateSession;
  setup: DebateSetup;
  onFinish: (review: DebateReview) => void;
}) {
  const reduceMotion = useReducedMotion();
  const [phase, setPhase] = useState<Phase>("turn");
  const [turnNumber, setTurnNumber] = useState(1);
  const [opponentLine, setOpponentLine] = useState<string | null>(null);
  const [opponentAudioAvailable, setOpponentAudioAvailable] = useState(false);
  const [opponentAudioUrl, setOpponentAudioUrl] = useState<string | null>(null);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [clip, setClip] = useState<Blob | null>(null);
  const [turnText, setTurnText] = useState<string | null>(null);
  const [clipUrl, setClipUrl] = useState<string | null>(null);
  const [slowResponse, setSlowResponse] = useState(false);
  const [turnError, setTurnError] = useState<string | null>(null);
  const [micDenied, setMicDenied] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const opponentReadyTimestampRef = useRef<number>(Date.now());
  const delayMsRef = useRef<number>(0);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const sessionRef = useRef<DebateSession>(session);
  noteCurrentSession(session);

  const total = session.totalUserTurns;

  // rally dots: teal (you) / coral (Rebutio) pairs
  const rally = Array.from({ length: total }, (_, i) => ({
    user: i + 1 < turnNumber || (i + 1 === turnNumber && ["submitted", "thinking", "opponent", "finished", "reviewing"].includes(phase)),
    opponent: i + 1 < turnNumber || (i + 1 === turnNumber && ["opponent", "finished", "reviewing"].includes(phase)),
    current: i + 1 === turnNumber && !["finished", "reviewing"].includes(phase),
  }));

  const tick = useCallback((p: Phase) => {
    if (p === "thinking" || p === "reviewing") {
      setSlowResponse(false);
      const t = setTimeout(() => setSlowResponse(true), 8000);
      return () => clearTimeout(t);
    }
  }, []);

  useEffect(() => tick(phase), [phase, tick]);

  useEffect(() => {
    if (phase !== "recording") return;
    setElapsed(0);
    const iv = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(iv);
  }, [phase]);

  function toggleOpponentAudio() {
    if (!opponentAudioUrl) return;

    if (!audioPlayerRef.current) {
      const audio = new Audio(opponentAudioUrl);
      audioPlayerRef.current = audio;
      audio.onplay = () => {
        setIsPlayingAudio(true);
        logger.debug("debate_flow.opponent_audio_play_started", { turnNumber });
      };
      audio.onpause = () => setIsPlayingAudio(false);
      audio.onended = () => {
        setIsPlayingAudio(false);
        opponentReadyTimestampRef.current = Date.now();
        logger.debug("debate_flow.opponent_audio_play_ended", { turnNumber });
      };
      audio.onerror = () => {
        logger.warn("debate_flow.opponent_audio_play_failed", { turnNumber });
        setIsPlayingAudio(false);
      };
    }

    const audio = audioPlayerRef.current;
    if (!audio.paused) {
      audio.pause();
      logger.debug("debate_flow.opponent_audio_paused", { turnNumber });
      return;
    }

    audio.play().catch((err) => {
      logger.warn("debate_flow.opponent_audio_play_blocked", { turnNumber });
      setIsPlayingAudio(false);
    });
  }

  useEffect(() => {
    const audio = audioPlayerRef.current;
    if (audio) {
      audio.pause();
      audioPlayerRef.current = null;
    }
    setIsPlayingAudio(false);
  }, [opponentAudioUrl]);

  useEffect(() => () => {
    audioPlayerRef.current?.pause();
    audioPlayerRef.current = null;
  }, []);

  async function startRecording() {
    try {
      delayMsRef.current = opponentReadyTimestampRef.current ? Math.max(0, Date.now() - opponentReadyTimestampRef.current) : 0;
      await capture.startRecording();
      setClip(null);
      setMicDenied(false);
      setPhase("recording");
      logger.info("debate_flow.recording_started", { turnNumber, delayMs: delayMsRef.current });
    } catch (err) {
      logger.warn("debate_flow.mic_denied", { turnNumber });
      setMicDenied(true);
    }
  }

  async function stopRecording() {
    try {
      const blob = await capture.stopRecording();
      if (blob) {
        setClip(blob);
        setClipUrl((old) => {
          if (old) URL.revokeObjectURL(old);
          return URL.createObjectURL(blob);
        });
      }
      setPhase("reviewing-clip");
      logger.info("debate_flow.recording_stopped", { turnNumber });
    } catch (err) {
      logger.error("debate_flow.recording_save_failed", { turnNumber }, err);
      setPhase("turn");
      setTurnError("Recording didn't save. Try again.");
    }
  }

  async function submitTurn() {
    sessionRef.current = { ...sessionRef.current, currentTurn: turnNumber };
    try {
      // intentional pacing: "Point submitted" beat, then thinking state
      // while the service resolves — waiting feels like part of the debate.
      setPhase("submitted");
      await new Promise((r) => setTimeout(r, reduceMotion ? 300 : 900));
      setPhase("thinking");
      logger.info("debate_flow.turn_submitted", { turnNumber, sessionId: sessionRef.current.id });
      const res = await appService.submitUserTurn(sessionRef.current, {
        audio: clip ?? undefined,
        transcript: turnText ?? undefined,
        clientResponseDelayMs: delayMsRef.current,
      });
      const turnsToAdd = [res.userTurn];
      if (res.opponentTurn) {
        turnsToAdd.push(res.opponentTurn);
      }
      sessionRef.current = {
        ...sessionRef.current,
        turns: [...sessionRef.current.turns, ...turnsToAdd],
      };
      if (res.opponentTurn) {
        setOpponentLine(res.opponentTurn.text ?? null);
        setOpponentAudioAvailable(Boolean(res.opponentTurn.playback?.available));
        setOpponentAudioUrl(res.opponentTurn.playback?.audioUrl ?? null);
      }
      opponentReadyTimestampRef.current = Date.now();
      if (res.finished) {
        setPhase("finished");
        logger.info("debate_flow.session_finished", { sessionId: sessionRef.current.id });
        await new Promise((r) => setTimeout(r, reduceMotion ? 400 : 1600));
        setPhase("reviewing");
        try {
          const review = await appService.getDebateReview(sessionRef.current.id);
          await appService.finishDebate(sessionRef.current);
          onFinish(review);
        } catch (err) {
          logger.warn("debate_flow.review_fetch_failed_using_fallback", { sessionId: sessionRef.current.id });
          // review unavailable — debate still counts as completed
          onFinish({
            outcome: "undetermined",
            topic: sessionRef.current.topic,
            skillName: sessionRef.current.skillTarget.name,
            stars: { stars: 1, completed: true, skillDemonstrated: false },
            xpEarned: 60,
            streakExtended: true,
          });
        }
      } else {
        setPhase("opponent");
        logger.info("debate_flow.opponent_turn_rendered", { turnNumber });
      }
    } catch (err: any) {
      logger.error("debate_flow.submit_turn_failed", { turnNumber, requestId: err?.requestId }, err);
      setTurnError("Couldn't send that turn. Try again.");
      setPhase("reviewing-clip");
    }
  }

  function nextTurn() {
    audioPlayerRef.current?.pause();
    audioPlayerRef.current = null;
    setIsPlayingAudio(false);
    setOpponentLine(null);
    setOpponentAudioAvailable(false);
    setOpponentAudioUrl(null);
    setClip(null);
    setTurnText(null);
    setTurnNumber((n) => Math.min(n + 1, total));
    setPhase("turn");
  }

  function retrySubmit() {
    setTurnError(null);
    setPhase("reviewing-clip");
  }

  const lastTurn = turnNumber === total;

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col px-5 pb-8 pt-5">
      {/* header */}
      <div className="mb-1 text-center">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">
          {["finished", "reviewing"].includes(phase) ? "Debate finished" : `Turn ${turnNumber} of ${total}`}
        </p>
        <p className="font-display text-lg font-bold leading-tight">{session.topic}</p>
      </div>

      {/* rally dots — the back-and-forth made visible */}
      <div className="my-4 flex items-center justify-center gap-2" aria-label={`Rally progress: turn ${turnNumber} of ${total}`}>
        {rally.map((r, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className={`h-3 w-3 rounded-full ${r.user ? "bg-rally" : "bg-ink/15"} ${r.current && ["turn", "recording", "reviewing-clip"].includes(phase) ? "ring-2 ring-rally ring-offset-2 ring-offset-parchment" : ""}`} />
            <span className={`h-3 w-3 rounded-full ${r.opponent ? "bg-coral" : "bg-ink/15"}`} />
            {i < total - 1 && <span className="h-px w-3 bg-ink/15" />}
          </div>
        ))}
      </div>

      <div className="flex flex-1 flex-col">
        <AnimatePresence mode="wait">
          {/* ---------- user's turn ---------- */}
          {(phase === "turn" || phase === "recording" || phase === "reviewing-clip") && (
            <motion.section key={`turn-${turnNumber}-${phase}`} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} className="flex flex-1 flex-col">
              <div className="mb-5 rounded-3xl bg-rally-mist px-5 py-4 text-center">
                <p className="font-display text-xl font-bold text-rally-deep">{skillLabel(session.skillTarget.name)}</p>
                <p className="mt-1 text-sm text-ink-soft">{session.skillReminder}</p>
              </div>

              {micDenied && (
                <div role="alert" className="mb-4 rounded-2xl bg-coral-soft px-4 py-3 text-sm font-medium text-coral">
                  Microphone unavailable. Make your point in text instead — the debate continues the same way.
                </div>
              )}

              {phase === "turn" && (
                <div className="flex flex-1 flex-col items-center justify-center gap-6">
                  {micDenied ? (
                    <TextFallback onSend={(t) => { setClip(null); setTurnText(t); setPhase("reviewing-clip"); }} />
                  ) : (
                    <>
                      <MicButton onClick={startRecording} label="Start speaking" />
                      <p className="text-sm text-ink-soft">Tap the mic and make your point. Take your time.</p>
                    </>
                  )}
                </div>
              )}

              {phase === "recording" && (
                <div className="flex flex-1 flex-col items-center justify-center gap-6">
                  <MicButton recording onClick={stopRecording} label="Stop speaking" elapsed={elapsed} />
                  <p className="text-sm font-medium text-coral">Recording — tap to finish your turn</p>
                </div>
              )}

              {phase === "reviewing-clip" && (
                <div className="flex flex-1 flex-col items-center justify-center gap-4">
                  <p className="font-display text-xl font-bold">Turn recorded</p>
                  {clipUrl ? (
                    <audio src={clipUrl} controls className="w-full max-w-xs" aria-label="Your recorded turn" />
                  ) : turnText ? (
                    <p className="max-w-xs rounded-2xl bg-white p-4 text-sm leading-relaxed shadow-[0_4px_18px_rgba(34,39,31,0.06)]">“{turnText}”</p>
                  ) : (
                    <p className="text-sm text-ink-soft">Recorded without audio capture.</p>
                  )}
                  {turnError && (
                    <p role="alert" className="rounded-2xl bg-coral-soft px-4 py-2 text-sm font-medium text-coral">
                      {turnError}
                    </p>
                  )}
                  <div className="mt-2 flex w-full max-w-xs flex-col gap-3">
                    <PrimaryButton onClick={submitTurn}>{lastTurn ? "Send final turn" : "Send turn"}</PrimaryButton>
                    <button onClick={() => setPhase("turn")} className="text-sm font-medium text-ink-soft underline underline-offset-4">
                      Re-record
                    </button>
                  </div>
                </div>
              )}
            </motion.section>
          )}

          {/* ---------- point submitted ---------- */}
          {phase === "submitted" && (
            <motion.section key="submitted" initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} className="flex flex-1 flex-col items-center justify-center gap-3">
              <motion.div initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: "spring", stiffness: 300, damping: 18 }} className="flex h-16 w-16 items-center justify-center rounded-full bg-rally text-3xl text-white">
                ✓
              </motion.div>
              <p className="font-display text-2xl font-bold">Point submitted</p>
            </motion.section>
          )}

          {/* ---------- thinking ---------- */}
          {phase === "thinking" && <ThinkingState slow={slowResponse} key="thinking" />}

          {/* ---------- opponent response ---------- */}
          {phase === "opponent" && (
            <motion.section key="opponent" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="flex flex-1 flex-col">
              <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-coral">Rebutio responds</p>
              <div className="relative rounded-3xl rounded-bl-lg bg-white p-5 shadow-[0_6px_24px_rgba(34,39,31,0.08)]">
                <OpponentResponseText text={opponentLine ?? "…"} />
                {opponentAudioAvailable && (
                  <button
                    onClick={toggleOpponentAudio}
                    className="mt-4 flex items-center gap-2 rounded-full bg-coral-soft px-4 py-2 text-sm font-semibold text-coral transition-colors hover:bg-coral-soft/80"
                    aria-label={isPlayingAudio ? "Pause opponent audio" : "Play opponent audio"}
                  >
                    <span aria-hidden>{isPlayingAudio ? "⏸" : "▶"}</span> {isPlayingAudio ? "Pause response" : "Play response"}
                  </button>
                )}
              </div>
              <div className="mt-6 flex flex-1 flex-col items-center justify-end gap-4 pb-2">
                <p className="text-sm font-medium text-ink-soft">{lastTurn ? "Prepare your closing argument." : "Prepare your rebuttal."}</p>
                <PrimaryButton onClick={nextTurn}>{lastTurn ? "Make my final point" : "Make my point"}</PrimaryButton>
              </div>
            </motion.section>
          )}

          {/* ---------- finished ---------- */}
          {phase === "finished" && (
            <motion.section key="finished" className="flex flex-1 flex-col items-center justify-center gap-3">
              <motion.div initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: "spring", stiffness: 260, damping: 16 }} className="text-5xl" aria-hidden>
                🏁
              </motion.div>
              <p className="font-display text-2xl font-bold">Debate finished</p>
              <p className="text-sm text-ink-soft">Both sides argued well.</p>
            </motion.section>
          )}

          {/* ---------- reviewing ---------- */}
          {phase === "reviewing" && <ReviewingState slow={slowResponse} key="reviewing" />}
        </AnimatePresence>
      </div>
    </div>
  );
}

function OpponentResponseText({ text }: { text: string }) {
  const textId = useId();
  const textRef = useRef<HTMLParagraphElement | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [canExpand, setCanExpand] = useState(false);

  useLayoutEffect(() => {
    const element = textRef.current;
    if (!element || expanded) return;

    const measureOverflow = () => {
      setCanExpand(element.scrollHeight > element.clientHeight + 1);
    };

    measureOverflow();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measureOverflow);
    observer.observe(element);
    return () => observer.disconnect();
  }, [expanded, text]);

  return (
    <div>
      <p
        id={textId}
        ref={textRef}
        tabIndex={expanded ? 0 : undefined}
        aria-label={expanded ? "Rebutio response. Scroll to read the full response." : undefined}
        className={`font-display text-[1.05rem] font-semibold leading-relaxed [overflow-wrap:anywhere] ${
          expanded
            ? "max-h-56 overflow-y-auto overscroll-contain pe-2 [scrollbar-color:var(--color-coral)_transparent] [scrollbar-width:thin]"
            : "overflow-hidden [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:5]"
        }`}
      >
        {text}
      </p>
      {canExpand && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          aria-controls={textId}
          aria-expanded={expanded}
          className="mt-3 text-sm font-semibold text-coral underline decoration-coral/35 underline-offset-4 transition-colors hover:text-ink"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
    </div>
  );
}

function TextFallback({ onSend }: { onSend: (t: string) => void }) {
  const [text, setText] = useState("");
  return (
    <div className="w-full">
      <label htmlFor="turn-text" className="text-sm font-medium text-ink-soft">Your point</label>
      <textarea
        id="turn-text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        placeholder="Say what you'd say out loud…"
        className="mt-2 w-full rounded-2xl border-2 border-ink/10 bg-white p-4 text-sm outline-none focus:border-rally"
      />
      <button
        onClick={() => text.trim() && onSend(text.trim())}
        disabled={!text.trim()}
        className="mt-3 w-full rounded-full bg-rally py-3.5 font-semibold text-white disabled:bg-ink-soft/40"
      >
        Review my turn
      </button>
    </div>
  );
}

function skillLabel(name: string) {
  return name;
}

function MicButton({ recording, onClick, label, elapsed }: { recording?: boolean; onClick: () => void; label: string; elapsed?: number }) {
  const reduceMotion = useReducedMotion();
  return (
    <motion.button
      onClick={onClick}
      aria-label={label}
      animate={recording && !reduceMotion ? { scale: [1, 1.05, 1] } : {}}
      transition={{ repeat: Infinity, duration: 1.4, ease: "easeInOut" }}
      className="relative flex h-32 w-32 items-center justify-center rounded-full bg-rally text-white shadow-[0_10px_30px_rgba(18,122,99,0.35)]"
    >
      {recording && !reduceMotion && (
        <span className="absolute inset-0 animate-ping rounded-full bg-rally/30" aria-hidden />
      )}
      <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden>
        <rect x="9" y="2.5" width="6" height="12" rx="3" />
        <path d="M5 11a7 7 0 0014 0M12 18v3.5" />
      </svg>
      {recording && elapsed !== undefined && (
        <span className="absolute -bottom-9 text-sm font-semibold text-coral">
          {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}
        </span>
      )}
    </motion.button>
  );
}

function PrimaryButton({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      onClick={onClick}
      className="w-full rounded-full bg-rally py-4 text-base font-semibold text-white shadow-[0_6px_20px_rgba(18,122,99,0.3)]"
    >
      {children}
    </motion.button>
  );
}

/** Signature motion: two sparring dots cross back and forth while Rebutio thinks. */
export function ThinkingState({ slow }: { slow: boolean }) {
  const reduceMotion = useReducedMotion();
  return (
    <section className="flex flex-1 flex-col items-center justify-center gap-8">
      <div className="relative h-10 w-40" aria-hidden>
        <motion.span
          className="absolute top-0 h-4 w-4 rounded-full bg-rally"
          animate={reduceMotion ? {} : { x: [0, 128, 0] }}
          transition={{ repeat: Infinity, duration: 1.6, ease: "easeInOut" }}
        />
        <motion.span
          className="absolute bottom-0 h-4 w-4 rounded-full bg-coral"
          animate={reduceMotion ? {} : { x: [128, 0, 128] }}
          transition={{ repeat: Infinity, duration: 1.6, ease: "easeInOut" }}
        />
      </div>
      <div className="text-center">
        <p className="font-display text-xl font-bold">Rebutio is thinking through your point…</p>
        {slow && <p className="mt-2 text-sm text-ink-soft">Taking longer than usual — hang tight.</p>}
      </div>
    </section>
  );
}

/** Final review: two argument cards weighed on a subtle balance. */
function ReviewingState({ slow }: { slow: boolean }) {
  const reduceMotion = useReducedMotion();
  return (
    <section className="flex flex-1 flex-col items-center justify-center gap-8">
      <div className="relative flex items-end gap-3" aria-hidden>
        <motion.div
          animate={reduceMotion ? {} : { rotate: [-3, 3, -3] }}
          transition={{ repeat: Infinity, duration: 2.4, ease: "easeInOut" }}
          className="flex h-24 w-20 items-center justify-center rounded-2xl bg-rally-mist"
        >
          <span className="text-2xl">🗣️</span>
        </motion.div>
        <div className="h-16 w-1 rounded bg-ink/20" />
        <motion.div
          animate={reduceMotion ? {} : { rotate: [3, -3, 3] }}
          transition={{ repeat: Infinity, duration: 2.4, ease: "easeInOut" }}
          className="flex h-24 w-20 items-center justify-center rounded-2xl bg-coral-soft"
        >
          <span className="text-2xl">🤖</span>
        </motion.div>
      </div>
      <div className="text-center">
        <p className="font-display text-xl font-bold">Reviewing both sides…</p>
        {slow && <p className="mt-2 text-sm text-ink-soft">A thorough review takes a moment.</p>}
      </div>
    </section>
  );
}
