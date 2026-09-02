"use client";

// Home answers one question: what debate should I do next?

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Button } from "@/components/shared/Button";
import { StarRow } from "@/components/shared/StarRow";
import { TabBar } from "@/components/shared/TabBar";
import { appService, skillName } from "@/lib/api";
import { getEffectivePath, mockDebateTopics } from "@/lib/mock/fixtures";
import { useStore } from "@/lib/state/store";
import type { DebateSession } from "@/lib/types";

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

  return (
    <main className="mx-auto min-h-dvh w-full max-w-md px-5 pb-28 pt-6">
      {/* compact stats */}
      <div className="flex items-center justify-between text-sm font-semibold">
        <span className="rounded-full bg-amber-soft px-3.5 py-1.5 text-amber-900">🔥 {streakDays}</span>
        <span className="font-display text-lg font-bold">Rebutio</span>
        <span className="rounded-full bg-rally-mist px-3.5 py-1.5 text-rally-deep">{(2460 + xp).toLocaleString()} XP</span>
      </div>

      {/* active unfinished debate banner if exists */}
      {activeSession && (
        <motion.section initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} className="mt-6">
          <div className="rounded-3xl bg-amber-soft border border-amber-300 p-5 shadow-[0_8px_30px_rgba(245,158,11,0.15)]">
            <div className="flex items-center justify-between">
              <span className="rounded-full bg-amber-200 px-3 py-1 text-xs font-bold uppercase tracking-wider text-amber-900">In Progress</span>
              <span className="text-xs font-semibold text-amber-800">
                Turn {activeSession.currentTurn}
              </span>
            </div>
            <h2 className="mt-3 font-display text-xl font-extrabold leading-snug text-amber-950">{activeSession.topic}</h2>
            <p className="mt-2 text-xs text-amber-900">
              Skill: <span className="font-semibold">{activeSession.skillTarget.name}</span> · Side: <span className="capitalize font-semibold">{activeSession.userSide}</span>
            </p>
            <Button
              onClick={() => router.push(`/debate?sessionId=${activeSession.id}`)}
              className="mt-4 w-full bg-amber-700 hover:bg-amber-800 text-white shadow-md"
            >
              Resume Debate
            </Button>
          </div>
        </motion.section>
      )}

      {/* today's spar — the largest element leads into speaking */}
      <motion.section initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} className="mt-8">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">Today&apos;s spar</p>
        <div className="mt-2 rounded-3xl bg-white p-5 shadow-[0_8px_30px_rgba(34,39,31,0.08)]">
          <h1 className="font-display text-2xl font-extrabold leading-snug">{dailyTopic.topic}</h1>
          <p className="mt-3 text-sm text-ink-soft">
            Skill: <span className="font-semibold text-ink">{skillName(dailyTopic.skill)}</span> · {dailyTopic.turns} turns · ~{dailyTopic.minutes} min
          </p>
          <div className="mt-4 flex gap-3">
            <span className="flex-1 rounded-full bg-rally-mist py-2 text-center text-sm font-semibold text-rally-deep">Agree</span>
            <span className="flex-1 rounded-full bg-coral-soft py-2 text-center text-sm font-semibold text-coral">Disagree</span>
          </div>
          <Button onClick={() => router.push(`/debate?topic=${dailyTopic.id}`)} className="mt-4 w-full">
            Start
          </Button>
        </div>
      </motion.section>

      {/* continue path */}
      <section className="mt-8">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">Continue path</p>
        <Link href="/path" className="mt-2 flex items-center gap-4 rounded-3xl bg-rally p-5 text-white shadow-[0_8px_24px_rgba(18,122,99,0.25)]">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-white/15 font-display text-lg font-bold" aria-hidden>
            {current.order}
          </span>
          <span className="flex-1">
            <span className="block font-display text-lg font-bold">{current.name}</span>
            <span className="block text-sm text-white/80">{current.topicPreview}</span>
          </span>
          <span aria-hidden>→</span>
        </Link>
      </section>

      {/* recent stars + next target skill */}
      <section className="mt-8 grid grid-cols-2 gap-3">
        <div className="rounded-3xl bg-white p-4 shadow-[0_4px_18px_rgba(34,39,31,0.06)]">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Recent stars</p>
          <div className="mt-2">
            <StarRow stars={3} size="sm" />
          </div>
          <p className="mt-1 text-xs text-ink-soft">Rebuttal · College debate</p>
        </div>
        <div className="rounded-3xl bg-white p-4 shadow-[0_4px_18px_rgba(34,39,31,0.06)]">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Next target</p>
          <p className="mt-2 font-display font-bold">{current.name}</p>
          <p className="mt-0.5 text-xs text-ink-soft">{current.description}</p>
        </div>
      </section>

      <TabBar />
    </main>
  );
}
