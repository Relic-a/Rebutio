"use client";

// Home answers one question: what debate should I do next?

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Button } from "@/components/shared/Button";
import { StarRow } from "@/components/shared/StarRow";
import { TabBar } from "@/components/shared/TabBar";
import { Logo } from "@/components/shared/Logo";
import { appService, skillName } from "@/lib/api";
import { getEffectivePath, mockDebateTopics } from "@/lib/mock/fixtures";
import { useStore } from "@/lib/state/store";
import type { DebateSession } from "@/lib/types";

const spring = { type: "spring", stiffness: 260, damping: 28 } as const;

export default function HomePage() {
  const router = useRouter();
  const onboarded = useStore((s) => s.onboarded);
  const xp = useStore((s) => s.xp);
  const streakDays = useStore((s) => s.streakDays);
  const starsByNodeId = useStore((s) => s.starsByNodeId);
  const [dailyTopic, setDailyTopic] = useState<(typeof mockDebateTopics)[number]>(() => {
    const day = new Date().getDate();
    return mockDebateTopics[day % mockDebateTopics.length];
  });
  const [activeSession, setActiveSession] = useState<DebateSession | null>(null);

  useEffect(() => {
    appService.getAppBootstrap().then((b) => {
      if (!b.onboarded) {
        router.replace("/onboarding");
      } else {
        if (b.activeSession) {
          setActiveSession(b.activeSession);
        }
      }
    }).catch(() => {
      if (!onboarded) router.replace("/onboarding");
    });

    appService.getDebateChoices().then((t) => {
      if (t && t.length > 0) {
        const day = new Date().getDate();
        setDailyTopic(t[day % t.length]);
      }
    }).catch(() => {});
  }, [onboarded, router]);

  if (!onboarded) return <main className="flex min-h-dvh items-center justify-center" />;

  const path = getEffectivePath(starsByNodeId);
  const current = path.nodes.find((n) => n.status === "current") ?? path.nodes[3];
  const totalXp = (2460 + xp).toLocaleString();

  return (
    <main className="mx-auto min-h-dvh w-full max-w-md px-4 pb-32 pt-5">
      {/* top bar */}
      <div className="flex items-center justify-between gap-3">
        <Logo size={26} />
        <div className="flex items-center gap-2 text-[13px] font-bold tabular-nums">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-900/15 bg-gradient-to-b from-[#fff7e6] to-amber-soft px-3 py-1.5 text-amber-deep shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]">
            <FlameIcon />
            {streakDays}
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-rally/20 bg-gradient-to-b from-white to-rally-mist px-3 py-1.5 text-rally-deep shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]">
            <XpIcon />
            {totalXp} XP
          </span>
        </div>
      </div>

      {/* active unfinished debate banner if exists */}
      {activeSession && (
        <motion.section initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={spring} className="mt-5">
          <div className="card-shell !border-amber-900/20">
            <div className="card-core bg-gradient-to-br from-[#fff8e8] to-amber-soft p-5">
              <div className="flex items-center justify-between">
                <span className="eyebrow bg-ink text-[#ffe9bd]">In progress · Turn {activeSession.currentTurn}</span>
                <span className="relative flex h-2.5 w-2.5" aria-hidden>
                  <span className="absolute h-full w-full animate-ring rounded-full bg-amber" />
                  <span className="h-2.5 w-2.5 rounded-full bg-amber" />
                </span>
              </div>
              <h2 className="mt-3 font-display text-xl font-black leading-snug text-amber-950">{activeSession.topic}</h2>
              <p className="mt-2 text-xs font-medium text-amber-900/80">
                {activeSession.skillTarget.name} · <span className="capitalize">{activeSession.userSide}</span> side
              </p>
              <Button
                onClick={() => router.push(`/debate?sessionId=${activeSession.id}`)}
                className="mt-4 w-full !bg-ink !text-[#ffe9bd] hover:!bg-black"
              >
                Resume debate
                <span aria-hidden>→</span>
              </Button>
            </div>
          </div>
        </motion.section>
      )}

      {/* Arena hero — today's spar */}
      <motion.section initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={spring} className="mt-5">
        <div className="card-shell-dark">
          <div className="card-core arena-panel relative overflow-hidden p-6 text-white">
            <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-amber/25 blur-3xl" aria-hidden />
            <div className="pointer-events-none absolute -bottom-20 -left-12 h-56 w-56 rounded-full bg-rally/40 blur-3xl" aria-hidden />
            {/* versus tick marks */}
            <div className="pointer-events-none absolute inset-x-6 top-5 flex justify-between opacity-30" aria-hidden>
              {Array.from({ length: 18 }).map((_, i) => (
                <span key={i} className="h-2 w-px bg-white/70" />
              ))}
            </div>

            <div className="relative">
              <div className="flex items-center justify-between">
                <span className="eyebrow bg-white/10 text-amber-200 ring-1 ring-white/20 backdrop-blur">
                  <span className="h-1.5 w-1.5 rounded-full bg-amber animate-pulse-soft" />
                  Today&apos;s spar
                </span>
                <span className="rounded-full bg-black/30 px-2.5 py-1 text-[11px] font-semibold text-white/80 ring-1 ring-white/15 tabular-nums">
                  ~{dailyTopic.minutes} min · {dailyTopic.turns} turns
                </span>
              </div>

              <h1 className="mt-4 font-display text-[2rem] font-black leading-[1.04] tracking-tight">{dailyTopic.topic}</h1>
              <p className="mt-3 inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 text-[13px] font-medium text-white/90 ring-1 ring-white/15 backdrop-blur">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-300" />
                Skill focus · <span className="font-bold text-white">{skillName(dailyTopic.skill)}</span>
              </p>

              <div className="mt-5 grid grid-cols-2 gap-2.5">
                <button
                  onClick={() => router.push(`/debate?topic=${dailyTopic.id}`)}
                  className="group rounded-2xl bg-[#f3fbf6] py-3 text-center text-sm font-black text-rally-deep shadow-[inset_0_1px_0_rgba(255,255,255,0.9)] transition-all duration-300 hover:-translate-y-0.5 hover:bg-white active:translate-y-0"
                >
                  <span className="block text-[10px] font-bold uppercase tracking-[0.16em] text-rally/70">Take side</span>
                  <span className="mt-0.5 flex items-center justify-center gap-1.5">
                    Agree
                    <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-rally text-[12px] text-white transition-transform duration-300 group-hover:translate-x-0.5" aria-hidden>→</span>
                  </span>
                </button>
                <button
                  onClick={() => router.push(`/debate?topic=${dailyTopic.id}`)}
                  className="group rounded-2xl bg-[#fff1ec] py-3 text-center text-sm font-black text-coral-deep shadow-[inset_0_1px_0_rgba(255,255,255,0.9)] transition-all duration-300 hover:-translate-y-0.5 hover:bg-white active:translate-y-0"
                >
                  <span className="block text-[10px] font-bold uppercase tracking-[0.16em] text-coral/70">Take side</span>
                  <span className="mt-0.5 flex items-center justify-center gap-1.5">
                    Disagree
                    <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-coral text-[12px] text-white transition-transform duration-300 group-hover:translate-x-0.5" aria-hidden>→</span>
                  </span>
                </button>
              </div>

              <Button onClick={() => router.push(`/debate?topic=${dailyTopic.id}`)} className="mt-3 w-full !bg-[#faf6ef] !text-ink hover:!bg-white">
                Enter the arena
              </Button>
              <p className="mt-2.5 text-center text-[11px] font-medium text-white/60">Live voice spar · No script · Coach listens in</p>
            </div>
          </div>
        </div>
      </motion.section>

      {/* continue path */}
      <motion.section initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.08 }} className="mt-4">
        <div className="flex items-baseline justify-between px-1">
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-ink-soft">Continue path</p>
          <Link href="/path" className="link-underline text-xs font-bold text-rally-deep">View all</Link>
        </div>
        <Link href="/path" className="card-shell group mt-2 block transition-transform duration-300 hover:-translate-y-0.5">
          <span className="card-core flex items-center gap-4 bg-gradient-to-br from-rally to-rally-deep p-4 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.25)]">
            <span className="relative flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-white/12 p-3.5 font-display text-lg font-black ring-1 ring-white/25" aria-hidden>
              {current.order}
              <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-amber text-[10px] text-ink shadow">▶</span>
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[10px] font-bold uppercase tracking-[0.18em] text-white/60">Level {current.order} · Up next</span>
              <span className="block truncate font-display text-lg font-black leading-tight">{current.name}</span>
              <span className="block truncate text-[13px] text-white/75">{current.topicPreview}</span>
            </span>
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-rally-deep transition-transform duration-300 group-hover:translate-x-1" aria-hidden>→</span>
          </span>
        </Link>
      </motion.section>

      {/* bento stats */}
      <section className="mt-4 grid grid-cols-5 gap-3">
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.12 }} className="card-paper col-span-3 rounded-[1.4rem] p-4">
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ink-soft">Last bout</p>
          <div className="mt-2">
            <StarRow stars={3} size="sm" />
          </div>
          <p className="mt-1.5 text-[13px] font-bold leading-tight">Sharp rebuttal under pressure</p>
          <p className="text-xs text-ink-soft">Rebuttal · College debate</p>
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.16 }} className="col-span-2 overflow-hidden rounded-[1.4rem] border border-rally-deep/25 bg-ink p-4 text-white shadow-[0_16px_32px_-16px_rgba(28,33,29,0.6)]">
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-white/55">Target</p>
          <p className="mt-2 font-display text-[15px] font-black leading-tight">{current.name}</p>
          <p className="mt-1 line-clamp-2 text-[11px] leading-snug text-white/65">{current.description}</p>
          <span className="mt-3 block h-1.5 overflow-hidden rounded-full bg-white/12">
            <span className="block h-full w-2/3 rounded-full bg-gradient-to-r from-amber to-emerald-300" />
          </span>
        </motion.div>
      </section>

      <TabBar />
    </main>
  );
}

function FlameIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 2c1 3.5-1.5 5.5-2.8 7.2C8 10.8 7 12 7 14a5 5 0 0 0 10 0c0-1.2-.4-2.3-1-3.3-.6 1-1.2 1.6-2 2.1.3-2.7-.6-6.6-2-10.8zM12 22a7 7 0 0 1-7-7c0-1.4.5-2.7 1.2-4 .4 1 1 1.9 1.9 2.6C8.5 10.9 10.4 8 11 4.5c.2-1 .4-2 .6-2.5h1c2.4 3.4 5.4 7.6 5.4 13a7 7 0 0 1-6 6.9z" opacity="0.95" />
    </svg>
  );
}

function XpIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M13 2L4.5 13.5H11L10 22l8.5-11.5H12L13 2z" />
    </svg>
  );
}
