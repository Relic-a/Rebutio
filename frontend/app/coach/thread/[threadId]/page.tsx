"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { appService } from "@/lib/api";
import { capture } from "@/lib/media/capture";
import { logger } from "@/lib/logger";
import { PronunciationText } from "@/components/coach/PronunciationText";
import type { CoachMessage, CoachThreadDetail } from "@/lib/types";

export default function GeneralCoachThreadPage() {
  const params = useParams();
  const router = useRouter();
  const threadId = params?.threadId as string;

  const [loading, setLoading] = useState(true);
  const [threadDetail, setThreadDetail] = useState<CoachThreadDetail | null>(null);
  const [messages, setMessages] = useState<CoachMessage[]>([]);
  const [textInput, setTextInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const recordingTimerRef = useRef<NodeJS.Timeout | null>(null);

  const scrollToBottom = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isSending, loading]);

  useEffect(() => {
    if (!threadId) return;
    setLoading(true);
    appService
      .getCoachThreadDetail(threadId)
      .then((detail) => {
        setThreadDetail(detail);
        setMessages(detail.messages || []);
        setLoading(false);
      })
      .catch((err) => {
        logger.error("coach.thread_load_failed", { threadId }, err);
        setErrorMsg("Could not load coaching thread.");
        setLoading(false);
      });
  }, [threadId]);

  async function handleSendText(promptText?: string) {
    const textToSend = promptText || textInput.trim();
    if (!textToSend || isSending || !threadDetail) return;

    setTextInput("");
    setIsSending(true);
    setErrorMsg(null);

    const tempUserMsg: CoachMessage = {
      id: `temp-${Date.now()}`,
      threadId,
      sender: "user",
      messageType: "text",
      text: textToSend,
      createdAt: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    try {
      const coachReply = await appService.sendCoachTextMessage(threadId, textToSend);
      setMessages((prev) => [...prev, coachReply]);
    } catch (err: any) {
      logger.error("coach.send_text_failed", { error: String(err) });
      setErrorMsg(err.message || "Failed to send message.");
    } finally {
      setIsSending(false);
    }
  }

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

      const res = await appService.sendCoachAudioMessage(threadId, rec.blob);
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
      <header className="flex shrink-0 items-center justify-between border-b border-ink/10 bg-white/90 px-4 py-3 backdrop-blur-md">
        <button
          onClick={() => router.push("/coach")}
          className="flex items-center gap-1.5 text-xs font-bold text-ink-soft hover:text-ink transition-colors"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <polyline points="15 18 9 12 15 6" />
          </svg>
          <span>Coach Home</span>
        </button>

        <div className="flex flex-col items-center text-center max-w-[60%]">
          <span className="text-[10px] font-bold uppercase tracking-wider text-rally">Coaching Session</span>
          <h1 className="truncate text-xs font-bold text-ink" title={threadDetail?.thread.title || "Coach Chat"}>
            {threadDetail?.thread.title || "Coach Chat"}
          </h1>
        </div>

        <div className="w-12" />
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 text-center text-ink-soft">
            <div className="w-8 h-8 border-2 border-rally border-t-transparent rounded-full animate-spin mb-3" />
            <p className="text-xs font-semibold">Connecting to your coach...</p>
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
                      {isCoach && m.text ? (
                        <PronunciationText text={m.text} className="whitespace-pre-wrap" />
                      ) : (
                        <p className="whitespace-pre-wrap">{m.text}</p>
                      )}
                      {m.messageType === "audio" && (
                        <div className="mt-1 flex items-center gap-1 text-[11px] opacity-80 font-mono">
                          <span>🎤 Spoken practice audio</span>
                          {m.durationSec && <span>({m.durationSec}s)</span>}
                        </div>
                      )}
                    </div>
                  </div>

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

      <footer className="shrink-0 border-t border-ink/10 bg-white p-3 shadow-lg">
        {errorMsg && (
          <div className="mb-2 rounded-xl bg-coral-soft/60 px-3 py-1.5 text-xs text-coral font-medium flex items-center justify-between">
            <span>{errorMsg}</span>
            <button onClick={() => setErrorMsg(null)} className="font-bold">×</button>
          </div>
        )}

        {isRecording ? (
          <div className="flex items-center justify-between bg-parchment rounded-2xl px-4 py-2.5">
            <button onClick={cancelAudioRecording} className="text-xs font-semibold text-ink-soft hover:text-ink">
              Cancel
            </button>
            <div className="flex items-center gap-2">
              <div className="w-2.5 h-2.5 rounded-full bg-coral animate-ping" />
              <span className="font-mono text-xs font-bold text-coral">
                Recording Practice: 0:{recordingSeconds < 10 ? `0${recordingSeconds}` : recordingSeconds} / 0:30
              </span>
            </div>
            <button onClick={stopAndSendAudio} className="rounded-full bg-rally px-4 py-1.5 text-xs font-bold text-white shadow hover:bg-rally/90">
              Send to Coach
            </button>
          </div>
        ) : (
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
              placeholder="Ask coach or request drills..."
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
