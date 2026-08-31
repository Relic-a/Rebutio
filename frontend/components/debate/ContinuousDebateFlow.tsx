"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { appService, noteCurrentSession } from "@/lib/api";
import { capture } from "@/lib/media/capture";
import { logger } from "@/lib/logger";
import type { DebateReview, DebateSession, DebateSetup, Speaker } from "@/lib/types";

type Phase =
  | "ready" // Waiting for user to speak/type
  | "recording" // User is recording audio
  | "processing" // Submitting turn to backend
  | "opponent_speaking" // Opponent response is playing/displayed
  | "finished";

interface StreamTurn {
  id: string;
  speaker: Speaker;
  text: string;
  audioUrl?: string;
  durationSec?: number;
  move?: string;
  timestamp: number;
}

export function ContinuousDebateFlow({
  session,
  setup,
  onFinish,
}: {
  session: DebateSession;
  setup: DebateSetup;
  onFinish: (review: DebateReview) => void;
}) {
  const [phase, setPhase] = useState<Phase>("ready");
  const [turnIndex, setTurnIndex] = useState(session.currentTurn || 1);
  const totalTurns = session.totalUserTurns || 3;

  // Stream of conversation turns
  const [turns, setTurns] = useState<StreamTurn[]>(() => {
    const initial: StreamTurn[] = [];
    if (session.turns && session.turns.length > 0) {
      session.turns.forEach((t, i) => {
        if (t.text) {
          initial.push({
            id: t.id || `init-${i}`,
            speaker: t.speaker,
            text: t.text,
            audioUrl: t.playback?.audioUrl,
            durationSec: t.durationSec,
            move: t.move,
            timestamp: Date.now() - (session.turns.length - i) * 10000,
          });
        }
      });
    }
    return initial;
  });

  // Composer states
  const [isTextMode, setIsTextMode] = useState(false);
  const [manualInput, setManualInput] = useState("");
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [micDenied, setMicDenied] = useState(false);
  const [turnError, setTurnError] = useState<string | null>(null);
  const [activeAudioPlaying, setActiveAudioPlaying] = useState<string | null>(null);
  const [elapsedDebateTime, setElapsedDebateTime] = useState(0);

  const turnsScrollRef = useRef<HTMLDivElement | null>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const recordingTimerRef = useRef<NodeJS.Timeout | null>(null);
  const currentSessionRef = useRef<DebateSession>(session);
  const submissionInFlightRef = useRef(false);

  noteCurrentSession(session);

  // Auto-scroll transcript stream
  const scrollToBottom = useCallback(() => {
    if (turnsScrollRef.current) {
      turnsScrollRef.current.scrollTop = turnsScrollRef.current.scrollHeight;
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [turns, phase, scrollToBottom]);

  // Overall debate timer
  useEffect(() => {
    const iv = setInterval(() => setElapsedDebateTime((t) => t + 1), 1000);
    return () => clearInterval(iv);
  }, []);

  // Format seconds mm:ss
  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s < 10 ? "0" : ""}${s}`;
  };

  // Play opponent audio if available
  const playTurnAudio = (turnId: string, url: string) => {
    if (activeAudioPlaying === turnId) {
      if (audioPlayerRef.current) {
        audioPlayerRef.current.pause();
        setActiveAudioPlaying(null);
      }
      return;
    }

    if (!audioPlayerRef.current) {
      audioPlayerRef.current = new Audio();
    }
    audioPlayerRef.current.src = url;
    audioPlayerRef.current.play().catch((e) => logger.warn("audio.play_failed", { error: String(e) }));
    setActiveAudioPlaying(turnId);

    audioPlayerRef.current.onended = () => {
      setActiveAudioPlaying(null);
    };
  };

  // Handle Recording Start
  async function startRecording() {
    setTurnError(null);
    setMicDenied(false);
    try {
      await capture.start();
      setPhase("recording");
      setRecordingSeconds(0);
      recordingTimerRef.current = setInterval(() => {
        setRecordingSeconds((s) => {
          if (s >= 58) {
            stopAndSubmitRecording();
            return 60;
          }
          return s + 1;
        });
      }, 1000);
    } catch (e: any) {
      logger.warn("mic.permission_denied", { error: String(e) });
      setMicDenied(true);
      setIsTextMode(true);
    }
  }

  // Handle Recording Cancel
  async function cancelRecording() {
    if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
    await capture.cancel();
    setPhase("ready");
    setRecordingSeconds(0);
  }

  // Handle Recording Stop & Submit
  async function stopAndSubmitRecording() {
    if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
    if (phase !== "recording") return;

    try {
      setPhase("processing");
      const rec = await capture.stop();
      if (!rec || rec.blob.size < 500) {
        throw new Error("No speech detected. Please speak clearly into your microphone.");
      }

      await submitTurn({ audio: rec.blob, clientResponseDelayMs: recordingSeconds * 1000 });
    } catch (err: any) {
      setTurnError(err.message || "Failed to process speech. You can type your response instead.");
      setPhase("ready");
    }
  }

  // Handle Manual Text Submit
  async function submitManualText() {
    if (!manualInput.trim() || phase === "processing") return;
    const text = manualInput.trim();
    setManualInput("");
    setTurnError(null);
    setPhase("processing");

    await submitTurn({ transcript: text });
  }

  // Turn submission execution
  async function submitTurn(turnPayload: { audio?: Blob; transcript?: string; clientResponseDelayMs?: number }) {
    // State updates are asynchronous, so phase alone cannot prevent two submit
    // handlers from entering during the same render (for example Enter + click).
    if (submissionInFlightRef.current) return;
    submissionInFlightRef.current = true;

    try {
      const userText = turnPayload.transcript || (turnPayload.audio ? "Spoken response submitted..." : "");

      // Optimistically add user turn to stream
      const optimisticUserTurnId = `u-${Date.now()}`;
      setTurns((prev) => [
        ...prev,
        {
          id: optimisticUserTurnId,
          speaker: "user",
          text: userText,
          durationSec: recordingSeconds || 5,
          timestamp: Date.now(),
        },
      ]);

      const result = await appService.submitUserTurn(currentSessionRef.current, turnPayload);

      // The API client derives turn_index from this session object. Keep it in
      // lockstep with the server response or every request after turn one is
      // mistaken for an idempotent retry of turn one.
      const returnedTurns = [result.userTurn, result.opponentTurn].filter(
        (turn): turn is DebateSession["turns"][number] => Boolean(turn)
      );
      const returnedTurnIds = new Set(returnedTurns.map((turn) => turn.id));
      currentSessionRef.current = {
        ...currentSessionRef.current,
        currentTurn: result.nextUserTurnNumber,
        status: result.finished ? "finished" : currentSessionRef.current.status,
        turns: [
          ...currentSessionRef.current.turns.filter((turn) => !returnedTurnIds.has(turn.id)),
          ...returnedTurns,
        ],
      };

      // Update user turn text if transcribed by STT backend
      if (result.userTurn && result.userTurn.text) {
        setTurns((prev) =>
          prev
            .filter((t) => t.id === optimisticUserTurnId || t.id !== result.userTurn.id)
            .map((t) =>
              t.id === optimisticUserTurnId
                ? { ...t, id: result.userTurn.id, text: result.userTurn.text || t.text }
                : t
            )
        );
      }

      if (result.opponentTurn && result.opponentTurn.text) {
        setPhase("opponent_speaking");
        const oppTurn: StreamTurn = {
          id: result.opponentTurn.id || `opp-${Date.now()}`,
          speaker: "opponent",
          text: result.opponentTurn.text,
          audioUrl: result.opponentTurn.playback?.audioUrl,
          durationSec: result.opponentTurn.durationSec,
          move: result.opponentTurn.move,
          timestamp: Date.now(),
        };

        setTurns((prev) => [...prev.filter((turn) => turn.id !== oppTurn.id), oppTurn]);

        // If audio playback is available, play it
        if (result.opponentTurn.playback?.audioUrl) {
          playTurnAudio(oppTurn.id, result.opponentTurn.playback.audioUrl);
        }
      }

      setTurnIndex(result.nextUserTurnNumber);

      if (result.finished) {
        setPhase("finished");
        // Fetch debate review and complete
        try {
          const review = await appService.getDebateReview(session.id);
          onFinish(review);
        } catch (revErr) {
          logger.error("debate.review_fetch_failed", { sessionId: session.id }, revErr);
          // Fallback minimal review
          onFinish({
            sessionId: session.id,
            outcome: "user_win",
            stars: { stars: 2, completed: true, skillDemonstrated: true, masteryNote: "Completed all debate rounds." },
            xpEarned: 120,
            streakExtended: true,
            topic: session.topic,
            skillName: session.skillTarget.name,
            scoreTechnique: { score: 8, label: "Debate Technique", rubric: "Directly challenged the opponent's core premise." },
            scoreGrammar: { score: 8, label: "Grammar & Accuracy", rubric: "Clean sentence structures without major breakdowns." },
            scoreVocabulary: { score: 8, label: "Vocabulary & Precision", rubric: "Persuasive and appropriate terminology." },
            scoreDelivery: { score: 8, label: "Delivery & Clarity", rubric: "Clear and confident pacing under conversational pressure." },
            strongestMoment: "Strongest moment in turn 2 when pressing the counterpoint.",
            improvementOpportunity: "Lead with your main thesis before elaborating on sub-points.",
          });
        }
      } else {
        // Return to ready state for next turn
        setTimeout(() => {
          setPhase("ready");
        }, 1200);
      }
    } catch (err: any) {
      logger.error("debate.turn_submission_error", { error: String(err) });
      setTurnError(err.message || "Failed to send response. Please try again.");
      setPhase("ready");
    } finally {
      submissionInFlightRef.current = false;
    }
  }

  // Format move label for display
  const formatMoveLabel = (moveKey?: string) => {
    if (!moveKey) return null;
    const map: Record<string, string> = {
      challenge_assumption: "Challenging your assumption",
      ask_clarification: "Clarification request",
      counterexample: "Presenting counterexample",
      request_evidence: "Demanding evidence",
      concede_and_press: "Conceding & pressing advantage",
      answer_user_question: "Direct response to your question",
      closing_challenge: "Closing challenge",
    };
    return map[moveKey] || moveKey.replace(/_/g, " ");
  };

  return (
    <main className="mx-auto flex h-dvh w-full max-w-lg flex-col bg-parchment text-ink">
      {/* 1. Header: Topic, Soft Timer, Finish Control */}
      <header className="flex shrink-0 items-center justify-between border-b border-ink/10 bg-white/80 px-4 py-3 backdrop-blur-md">
        <div className="flex flex-col min-w-0 pr-3">
          <div className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[10px] font-bold uppercase tracking-wider text-ink-soft">
              Live Debate Spar
            </span>
          </div>
          <h1 className="truncate text-sm font-bold text-ink" title={session.topic}>
            {session.topic}
          </h1>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <div className="flex items-center gap-1 rounded-full bg-parchment px-2.5 py-1 text-xs font-semibold text-ink-soft">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            <span>{formatTime(elapsedDebateTime)}</span>
          </div>

          <button
            onClick={() => {
              if (confirm("Conclude this debate and review your performance now?")) {
                appService.finishDebate(session).then(() => {
                  appService.getDebateReview(session.id).then(onFinish);
                });
              }
            }}
            className="rounded-full bg-ink/5 px-3 py-1 text-xs font-semibold text-ink hover:bg-coral/10 hover:text-coral transition-colors"
            title="Conclude debate"
          >
            Finish
          </button>
        </div>
      </header>

      {/* 2. Target Skill Banner */}
      <div className="shrink-0 bg-rally-mist/50 px-4 py-2 border-b border-rally/10 flex items-center justify-between text-xs text-rally-deep">
        <span className="font-semibold">Focus: {session.skillTarget.name}</span>
        <span className="text-ink-soft text-[11px]">{session.userSide === "agree" ? "Your Stance: Agree" : "Your Stance: Disagree"}</span>
      </div>

      {/* 3. Continuous Conversation Stream */}
      <div ref={turnsScrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4 scroll-smooth">
        {turns.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-center text-ink-soft">
            <div className="w-12 h-12 rounded-full bg-rally-mist flex items-center justify-center text-rally mb-3">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="22" />
              </svg>
            </div>
            <p className="text-sm font-semibold text-ink">The floor is yours.</p>
            <p className="text-xs mt-1 max-w-xs">
              Press the microphone below and speak your opening argument supporting your side.
            </p>
          </div>
        )}

        {turns.map((t) => {
          const isOpponent = t.speaker === "opponent";
          const moveBadge = formatMoveLabel(t.move);

          return (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex flex-col ${isOpponent ? "items-start" : "items-end"}`}
            >
              {/* Opponent Move Badge */}
              {isOpponent && moveBadge && (
                <div className="mb-1.5 ml-1 flex items-center gap-1 text-[11px] font-semibold text-coral bg-coral-soft/50 px-2 py-0.5 rounded-md">
                  <span className="w-1.5 h-1.5 rounded-full bg-coral animate-pulse" />
                  {moveBadge}
                </div>
              )}

              <div className="flex items-end gap-2 max-w-[85%]">
                {isOpponent && (
                  <div className="w-7 h-7 rounded-full bg-coral flex items-center justify-center text-white text-xs font-bold shrink-0 mb-1">
                    R
                  </div>
                )}

                <div
                  className={`rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                    isOpponent
                      ? "bg-white text-ink rounded-bl-sm border border-ink/10"
                      : "bg-rally text-white rounded-br-sm"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{t.text}</p>

                  {/* Audio Playback pill if available */}
                  {t.audioUrl && (
                    <button
                      onClick={() => playTurnAudio(t.id, t.audioUrl!)}
                      className={`mt-2 flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full transition-colors ${
                        isOpponent
                          ? "bg-coral-soft text-coral hover:bg-coral-soft/80"
                          : "bg-white/20 text-white hover:bg-white/30"
                      }`}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                        {activeAudioPlaying === t.id ? (
                          <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
                        ) : (
                          <polygon points="5 3 19 12 5 21 5 3" />
                        )}
                      </svg>
                      <span>{activeAudioPlaying === t.id ? "Pause" : "Listen to audio"}</span>
                    </button>
                  )}
                </div>
              </div>
            </motion.div>
          );
        })}

        {/* Live Processing Indicator */}
        {phase === "processing" && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-2 text-xs text-ink-soft py-2">
            <div className="flex gap-1">
              <span className="w-2 h-2 rounded-full bg-rally animate-bounce" />
              <span className="w-2 h-2 rounded-full bg-rally animate-bounce [animation-delay:0.2s]" />
              <span className="w-2 h-2 rounded-full bg-rally animate-bounce [animation-delay:0.4s]" />
            </div>
            <span>Rebutio is formulating a response...</span>
          </motion.div>
        )}
      </div>

      {/* 4. Compact Status Indicator */}
      <div className="shrink-0 px-4 py-1.5 text-center text-xs font-medium text-ink-soft border-t border-ink/5 bg-parchment/60">
        {phase === "ready" && "Your turn to respond"}
        {phase === "recording" && `Listening... ${recordingSeconds}s`}
        {phase === "processing" && "Processing what you said..."}
        {phase === "opponent_speaking" && "Rebutio is responding..."}
        {phase === "finished" && "Debate concluded. Preparing evaluation..."}
      </div>

      {/* 5. Persistent Bottom Composer (Voice + Text Mode) */}
      <footer className="shrink-0 border-t border-ink/10 bg-white p-4 shadow-lg">
        {turnError && (
          <div className="mb-3 rounded-xl bg-coral-soft/60 px-3 py-2 text-xs text-coral font-medium flex items-center justify-between">
            <span>{turnError}</span>
            <button onClick={() => setTurnError(null)} className="ml-2 font-bold">×</button>
          </div>
        )}

        {isTextMode ? (
          /* Text Composer Mode */
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <textarea
                value={manualInput}
                onChange={(e) => setManualInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submitManualText();
                  }
                }}
                placeholder="Type your point, question, or clarification (Enter to send)..."
                rows={2}
                disabled={phase === "processing"}
                className="flex-1 resize-none rounded-xl border border-ink/20 bg-parchment px-3 py-2 text-sm text-ink placeholder:text-ink-soft focus:border-rally focus:outline-none"
              />
              <button
                onClick={submitManualText}
                disabled={!manualInput.trim() || phase === "processing"}
                className="h-10 w-10 rounded-xl bg-rally text-white flex items-center justify-center font-bold disabled:opacity-40 transition-opacity"
                title="Send turn"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              </button>
            </div>

            <div className="flex items-center justify-between text-xs text-ink-soft">
              <span>Press Enter to send</span>
              <button
                onClick={() => setIsTextMode(false)}
                className="font-semibold text-rally hover:underline"
              >
                Switch to Voice
              </button>
            </div>
          </div>
        ) : (
          /* Voice Composer Mode */
          <div className="flex flex-col items-center">
            {phase === "recording" ? (
              /* Active Recording View */
              <div className="w-full flex items-center justify-between">
                <button
                  onClick={cancelRecording}
                  className="rounded-full px-4 py-2 text-xs font-semibold text-ink-soft hover:bg-ink/5"
                >
                  Cancel
                </button>

                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-coral animate-ping" />
                  <span className="font-mono text-sm font-bold text-coral">
                    0:{recordingSeconds < 10 ? `0${recordingSeconds}` : recordingSeconds} / 0:60
                  </span>
                </div>

                <button
                  onClick={stopAndSubmitRecording}
                  className="rounded-full bg-rally px-5 py-2 text-xs font-bold text-white shadow hover:bg-rally/90"
                >
                  Done speaking
                </button>
              </div>
            ) : (
              /* Idle / Ready to Record View */
              <div className="w-full flex items-center justify-between">
                <button
                  onClick={() => setIsTextMode(true)}
                  className="text-xs font-semibold text-ink-soft hover:text-ink flex items-center gap-1"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="2" y="4" width="20" height="16" rx="2" />
                    <line x1="6" y1="8" x2="6" y2="8" />
                    <line x1="10" y1="8" x2="10" y2="8" />
                    <line x1="14" y1="8" x2="14" y2="8" />
                    <line x1="18" y1="8" x2="18" y2="8" />
                    <line x1="6" y1="12" x2="18" y2="12" />
                    <line x1="6" y1="16" x2="14" y2="16" />
                  </svg>
                  <span>Type instead</span>
                </button>

                <button
                  onClick={startRecording}
                  disabled={phase === "processing" || phase === "finished"}
                  className="group relative flex h-14 w-14 items-center justify-center rounded-full bg-rally text-white shadow-lg transition-transform active:scale-95 disabled:opacity-50"
                  title="Press to speak"
                >
                  <div className="absolute inset-0 rounded-full bg-rally/30 group-hover:scale-110 transition-transform -z-10" />
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                    <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                    <line x1="12" y1="19" x2="12" y2="22" />
                  </svg>
                </button>

                <span className="text-xs text-ink-soft font-medium">Tap to Speak</span>
              </div>
            )}
          </div>
        )}
      </footer>
    </main>
  );
}
