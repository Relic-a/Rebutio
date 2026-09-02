"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { appService, getAuthenticatedMediaBlobUrl } from "@/lib/api";
import { capture } from "@/lib/media/capture";
import { logger } from "@/lib/logger";
import { PronunciationText } from "@/components/coach/PronunciationText";
import type { AudioEvidenceCard, CoachMessage, CoachThreadDetail, QuickReply } from "@/lib/types";

export default function SessionCoachPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params?.sessionId as string;

  const [loading, setLoading] = useState(true);
  const [threadDetail, setThreadDetail] = useState<CoachThreadDetail | null>(null);
  const [messages, setMessages] = useState<CoachMessage[]>([]);
  const [textInput, setTextInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [activeClipPlaying, setActiveClipPlaying] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const recordingTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Auto-scroll to latest message
  const scrollToBottom = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isSending, loading]);

  // Load session coaching thread
  useEffect(() => {
    if (!sessionId) return;
    setLoading(true);
    setErrorMsg(null);
    appService
      .getSessionCoachThread(sessionId)
      .then((detail) => {
        setThreadDetail(detail);
        setMessages(detail.messages || []);
        setErrorMsg(null);
        setLoading(false);
      })
      .catch((err) => {
        logger.error("coach.session_load_failed", { sessionId }, err);
        setErrorMsg("Could not load coaching session. Please try again.");
        setLoading(false);
      });
  }, [sessionId]);

  // Play audio evidence clip
  const playClip = async (clipId: string, url: string) => {
    if (activeClipPlaying === clipId) {
      if (audioPlayerRef.current) {
        audioPlayerRef.current.pause();
        setActiveClipPlaying(null);
      }
      return;
    }

    if (!audioPlayerRef.current) {
      audioPlayerRef.current = new Audio();
      audioPlayerRef.current.onended = () => {
        setActiveClipPlaying(null);
      };
      audioPlayerRef.current.onerror = () => {
        setActiveClipPlaying(null);
        setErrorMsg("Failed to play audio evidence clip.");
      };
    }

    const blobUrl = await getAuthenticatedMediaBlobUrl(url);
    if (!blobUrl) {
      setErrorMsg("Failed to load audio evidence clip.");
      setActiveClipPlaying(null);
      return;
    }

    audioPlayerRef.current.src = blobUrl;
    audioPlayerRef.current.play().catch((e) => {
      logger.warn("coach.audio_play_failed", { clipId, error: String(e) });
      setErrorMsg("Audio playback blocked by browser. Click again to play.");
      setActiveClipPlaying(null);
    });
    setActiveClipPlaying(clipId);
  };

  // Send text message
  async function handleSendText(promptText?: string) {
    const textToSend = promptText || textInput.trim();
    if (!textToSend || isSending || !threadDetail) return;

    setTextInput("");
    setIsSending(true);
    setErrorMsg(null);

    // Optimistic user message
    const tempUserMsg: CoachMessage = {
      id: `temp-${Date.now()}`,
      threadId: threadDetail.thread.id,
      sender: "user",
      messageType: "text",
      text: textToSend,
      createdAt: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    try {
      const coachReply = await appService.sendCoachTextMessage(threadDetail.thread.id, textToSend);
      setMessages((prev) => [...prev, coachReply]);
    } catch (err: any) {
      logger.error("coach.send_text_failed", { error: String(err) });
      setErrorMsg(err.message || "Failed to send message.");
    } finally {
      setIsSending(false);
    }
  }

  // Audio Recording Practice
  async function startAudioRecording() {
    setErrorMsg(null);
    try {
      await capture.start();
      setIsRecording(true);
      setRecordingSeconds(0);
      recordingTimerRef.current = setInterval(() => {
        setRecordingSeconds((s) => {
          if (s >= 30) {
            stopAndSendAudio();
            return 30;
          }
          return s + 1;
        });
      }, 1000);
    } catch (e: any) {
      logger.warn("coach.mic_denied", { error: String(e) });
      setErrorMsg("Microphone access denied.");
    }
  }

  async function cancelAudioRecording() {
    if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
    await capture.cancel();
    setIsRecording(false);
    setRecordingSeconds(0);
  }

  async function stopAndSendAudio() {
    if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
    if (!isRecording || !threadDetail) return;

    try {
      setIsRecording(false);
      setIsSending(true);
      const rec = await capture.stop();
      if (!rec || rec.blob.size < 500) {
        throw new Error("No speech recorded. Please speak clearly.");
      }

      const res = await appService.sendCoachAudioMessage(threadDetail.thread.id, rec.blob);
      if (res.userMessage && res.coachMessage) {
        setMessages((prev) => [...prev, res.userMessage, res.coachMessage]);
      }
    } catch (err: any) {
      logger.error("coach.audio_send_failed", { error: String(err) });
      setErrorMsg(err.message || "Failed to analyze speech recording.");
    } finally {
      setIsSending(false);
      setRecordingSeconds(0);
    }
  }

  return (
    <main className="mx-auto flex h-dvh w-full max-w-lg flex-col bg-parchment text-ink pb-2">
      {/* 1. Header: Navigation, Title & Topic */}
      <header className="flex shrink-0 items-center justify-between border-b border-ink/10 bg-white/90 px-4 py-3 backdrop-blur-md">
        <button
          onClick={() => router.push("/coach")}
          className="flex shrink-0 items-center gap-1 text-xs font-bold text-ink-soft hover:text-ink transition-colors w-24"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <polyline points="15 18 9 12 15 6" />
          </svg>
          <span>Coach Home</span>
        </button>

        <div className="flex flex-1 min-w-0 flex-col items-center text-center px-2">
          <span className="text-[10px] font-bold uppercase tracking-wider text-rally">Debate AI Coach</span>
          <h1 className="w-full truncate text-xs font-bold text-ink" title={threadDetail?.thread.topic || "Debate Review"}>
            {threadDetail?.thread.topic || "Debate Review"}
          </h1>
        </div>

        <button
          onClick={() => router.push("/results")}
          className="shrink-0 text-xs font-semibold text-ink-soft hover:text-ink w-16 text-right"
        >
          Results
        </button>
      </header>

      {/* 2. Message Scroll Area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 text-center text-ink-soft">
            <div className="w-8 h-8 border-2 border-rally border-t-transparent rounded-full animate-spin mb-3" />
            <p className="text-xs font-semibold">Your coach is analyzing your debate...</p>
          </div>
        ) : errorMsg && !threadDetail ? (
          <div className="flex flex-col items-center justify-center py-20 text-center text-ink-soft space-y-3">
            <p className="text-sm font-semibold text-coral">{errorMsg}</p>
            <button
              onClick={() => {
                setLoading(true);
                setErrorMsg(null);
                appService
                  .getSessionCoachThread(sessionId)
                  .then((detail) => {
                    setThreadDetail(detail);
                    setMessages(detail.messages || []);
                    setLoading(false);
                  })
                  .catch(() => {
                    setErrorMsg("Could not load coaching session. Please try again.");
                    setLoading(false);
                  });
              }}
              className="rounded-xl bg-rally px-4 py-2 text-xs font-bold text-white shadow hover:bg-rally/90"
            >
              Retry loading coach
            </button>
          </div>
        ) : (
          <>
            {messages.map((m) => {
              const isCoach = m.sender === "coach";

              return (
                <motion.div
                  key={m.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`flex flex-col ${isCoach ? "items-start" : "items-end"}`}
                >
                  {/* Proactive Opening Analysis Card */}
                  {m.messageType === "opening_analysis" && m.openingAnalysis && (
                    <div className="w-full rounded-2xl bg-white border border-rally/20 p-4 shadow-sm mb-2 space-y-3">
                      <div className="flex items-center gap-2 text-xs font-bold text-rally">
                        <span className="w-2 h-2 rounded-full bg-rally animate-pulse" />
                        <span>Debate Opening Analysis</span>
                      </div>

                      <PronunciationText text={m.openingAnalysis.overallAssessment} className="text-sm font-semibold text-ink leading-relaxed whitespace-pre-wrap" />

                      <div className="grid grid-cols-1 gap-2 pt-1">
                        <div className="rounded-xl bg-rally-mist/50 p-2.5 text-xs">
                          <span className="font-bold text-rally-deep">Standout Strength: </span>
                          <PronunciationText text={m.openingAnalysis.mostImportantStrength} className="inline text-ink" />
                        </div>
                        <div className="rounded-xl bg-amber-soft/50 p-2.5 text-xs">
                          <span className="font-bold text-amber-900">Highest-Value Growth: </span>
                          <PronunciationText text={m.openingAnalysis.highestValueImprovement} className="inline text-ink" />
                        </div>
                      </div>

                      {m.openingAnalysis.concreteExample && (
                        <p className="text-xs text-ink-soft italic bg-parchment p-2 rounded-lg">
                          &ldquo;{m.openingAnalysis.concreteExample}&rdquo;
                        </p>
                      )}
                    </div>
                  )}

                  {/* Standard Message Bubble */}
                  {m.text && (m.messageType !== "opening_analysis" || !m.openingAnalysis) && (
                    <div className="flex items-end gap-2 max-w-[85%]">
                      {isCoach && (
                        <div className="w-7 h-7 rounded-full bg-rally flex items-center justify-center text-white text-xs font-bold shrink-0 mb-1">
                          C
                        </div>
                      )}
                      <div
                        className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                          isCoach
                            ? "bg-white text-ink rounded-bl-sm border border-ink/10 shadow-sm"
                            : "bg-rally text-white rounded-br-sm shadow"
                        }`}
                      >
                        {isCoach ? (
                          <PronunciationText text={m.text} className="whitespace-pre-wrap" />
                        ) : (
                          <p className="whitespace-pre-wrap">{m.text}</p>
                        )}

                        {/* Audio recording badge if user sent audio */}
                        {m.messageType === "audio" && (
                          <div className="mt-1 flex items-center gap-1 text-[11px] opacity-80 font-mono">
                            <span>🎤 Spoken practice audio</span>
                            {m.durationSec && <span>({m.durationSec}s)</span>}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Interactive Evidence Player Card */}
                  {m.evidenceClip && (
                    <div className="mt-2 w-full max-w-[90%] rounded-2xl bg-white border border-coral/20 p-3.5 shadow-sm space-y-2.5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5 text-xs font-bold text-coral">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                            <polygon points="5 3 19 12 5 21 5 3" />
                          </svg>
                          <span>{m.evidenceClip.sourceLabel}</span>
                        </div>
                        <span className="font-mono text-[11px] text-ink-soft font-bold">
                          {m.evidenceClip.durationSec}s
                        </span>
                      </div>

                      <p className="text-xs text-ink bg-parchment p-2 rounded-lg font-medium">
                        &ldquo;{m.evidenceClip.transcriptExcerpt}&rdquo;
                      </p>

                      <p className="text-xs text-ink-soft">
                        <span className="font-semibold text-ink">What to notice: </span>
                        {m.evidenceClip.whatToNotice}
                      </p>

                      <button
                        onClick={() => playClip(m.evidenceClip!.clipId, m.evidenceClip!.audioUrl)}
                        className="w-full py-2 rounded-xl bg-coral-soft hover:bg-coral-soft/80 text-coral font-bold text-xs flex items-center justify-center gap-1.5 transition-colors"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                          {activeClipPlaying === m.evidenceClip.clipId ? (
                            <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
                          ) : (
                            <polygon points="5 3 19 12 5 21 5 3" />
                          )}
                        </svg>
                        <span>{activeClipPlaying === m.evidenceClip.clipId ? "Pause Clip" : "Play Recorded Clip"}</span>
                      </button>
                    </div>
                  )}

                  {/* Suggested Quick Replies */}
                  {m.quickReplies && m.quickReplies.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {m.quickReplies.map((qr, idx) => (
                        <button
                          key={idx}
                          onClick={() => handleSendText(qr.prompt)}
                          disabled={isSending}
                          className="rounded-full border border-rally/30 bg-white px-3 py-1 text-xs font-semibold text-rally hover:bg-rally-mist transition-colors disabled:opacity-50"
                        >
                          {qr.label}
                        </button>
                      ))}
                    </div>
                  )}
                </motion.div>
              );
            })}

            {/* Coach typing / thinking indicator */}
            {isSending && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-2 text-xs text-ink-soft py-2">
                <div className="flex gap-1">
                  <span className="w-2 h-2 rounded-full bg-rally animate-bounce" />
                  <span className="w-2 h-2 rounded-full bg-rally animate-bounce [animation-delay:0.2s]" />
                  <span className="w-2 h-2 rounded-full bg-rally animate-bounce [animation-delay:0.4s]" />
                </div>
                <span>Coach is thinking...</span>
              </motion.div>
            )}
          </>
        )}
      </div>

      {/* 3. Composer: Persistent Text Input + Practice Audio Recorder */}
      <footer className="shrink-0 border-t border-ink/10 bg-white p-3 shadow-lg">
        {errorMsg && (
          <div className="mb-2 rounded-xl bg-coral-soft/60 px-3 py-1.5 text-xs text-coral font-medium flex items-center justify-between">
            <span>{errorMsg}</span>
            <button onClick={() => setErrorMsg(null)} className="font-bold">×</button>
          </div>
        )}

        {isRecording ? (
          /* Active Voice Practice Recording Bar */
          <div className="flex items-center justify-between bg-parchment rounded-2xl px-4 py-2.5">
            <button
              onClick={cancelAudioRecording}
              className="text-xs font-semibold text-ink-soft hover:text-ink"
            >
              Cancel
            </button>

            <div className="flex items-center gap-2">
              <div className="w-2.5 h-2.5 rounded-full bg-coral animate-ping" />
              <span className="font-mono text-xs font-bold text-coral">
                Recording Practice: 0:{recordingSeconds < 10 ? `0${recordingSeconds}` : recordingSeconds} / 0:30
              </span>
            </div>

            <button
              onClick={stopAndSendAudio}
              className="rounded-full bg-rally px-4 py-1.5 text-xs font-bold text-white shadow hover:bg-rally/90"
            >
              Send to Coach
            </button>
          </div>
        ) : (
          /* Normal Composer Input */
          <div className="flex items-center gap-2">
            <button
              onClick={startAudioRecording}
              disabled={isSending}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-rally-mist text-rally hover:bg-rally-mist/80 disabled:opacity-40 transition-colors"
              title="Record practice response"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="22" />
              </svg>
            </button>

            <input
              type="text"
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleSendText();
                }
              }}
              placeholder="Ask coach or request practice drills..."
              disabled={isSending}
              className="flex-1 rounded-xl border border-ink/20 bg-parchment px-3.5 py-2 text-sm text-ink placeholder:text-ink-soft focus:border-rally focus:outline-none"
            />

            <button
              onClick={() => handleSendText()}
              disabled={!textInput.trim() || isSending}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-rally text-white font-bold disabled:opacity-40 transition-opacity"
              title="Send message"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>
        )}
      </footer>
    </main>
  );
}
