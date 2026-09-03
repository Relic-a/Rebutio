"use client";

// Progress: learning progress visually separate from competitive record.
// Winning debates ≠ speaking better English, so they live apart.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { TabBar } from "@/components/shared/TabBar";
import { appService } from "@/lib/api";
import { mockLearningPath, mockProgressStats } from "@/lib/mock/fixtures";
import { useStore } from "@/lib/state/store";
import type { ProgressStats } from "@/lib/types";

export default function ProgressPage() {
  const router = useRouter();
  const onboarded = useStore((s) => s.onboarded);
  const liveXp = useStore((s) => s.xp);
  const [stats, setStats] = useState<ProgressStats>(() => ({
    ...mockProgressStats,
    xp: mockProgressStats.xp + liveXp,
    debatesCompleted: mockProgressStats.debatesCompleted + (useStore.getState().debatesCompleted || 0),
  }));

  useEffect(() => {
    if (!onboarded) router.replace("/onboarding");
    appService.getProgress().then((s) => {
      if (s) setStats(s);
    }).catch(() => {});
  }, [onboarded, router]);

  if (!onboarded) return <main className="flex min-h-dvh items-center justify-center" />;

  // Use live stats from backend API with fallback
  const merged: ProgressStats = {
    ...stats,
    xp: stats.xp > 0 ? stats.xp : mockProgressStats.xp + liveXp,
    debatesCompleted: stats.debatesCompleted > 0 ? stats.debatesCompleted : mockProgressStats.debatesCompleted + useStore.getState().debatesCompleted,
  };
  const record = {
    wins: stats.debatesCompleted > 0 ? stats.wins : mockProgressStats.wins + useStore.getState().record.wins,
    losses: stats.debatesCompleted > 0 ? stats.losses : mockProgressStats.losses + useStore.getState().record.losses,
    draws: stats.debatesCompleted > 0 ? stats.draws : mockProgressStats.draws + useStore.getState().record.draws,
  };
  const current = mockLearningPath.nodes.find((n) => n.status === "current");

  return (
    <main className="mx-auto min-h-dvh w-full max-w-md px-4 pb-32 pt-6">
      <header className="card-shell-dark">
        <div className="card-core arena-panel relative overflow-hidden p-5 text-white">
          <div className="pointer-events-none absolute -right-12 -top-12 h-44 w-44 rounded-full bg-amber/25 blur-3xl" aria-hidden />
          <p className="relative text-[10px] font-bold uppercase tracking-[0.2em] text-white/60">Progress</p>
          <h1 className="relative mt-1 font-display text-[1.9rem] font-black tracking-tight">Your English is compounding</h1>
          <div className="relative mt-4 grid grid-cols-3 gap-2 text-center">
            <div className="rounded-2xl bg-white/10 p-3 ring-1 ring-white/15 backdrop-blur">
              <p className="font-display text-lg font-black tabular-nums">{merged.xp.toLocaleString()}</p>
              <p className="text-[10px] font-bold uppercase tracking-widest text-white/60">XP</p>
            </div>
            <div className="rounded-2xl bg-white/10 p-3 ring-1 ring-white/15 backdrop-blur">
              <p className="font-display text-lg font-black tabular-nums">{merged.debatesCompleted}</p>
              <p className="text-[10px] font-bold uppercase tracking-widest text-white/60">Debates</p>
            </div>
            <div className="rounded-2xl bg-[#ffe9bd] p-3 text-ink">
              <p className="font-display text-lg font-black tabular-nums">{stats.streakDays}d</p>
              <p className="text-[10px] font-bold uppercase tracking-widest text-ink-soft">Streak</p>
            </div>
          </div>
        </div>
      </header>

      {/* top line: level */}
      <div className="mt-4 rounded-[1.4rem] card-paper p-4 text-center">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-ink-soft">Path level</p>
        <p className="mt-1 font-display text-lg font-black">{mockLearningPath.levelName} {mockLearningPath.levelNumber}</p>
      </div>

      {/* learning progress */}
      <section className="mt-6">
        <h2 className="px-1 font-display text-xl font-black">Speaking</h2>
        <div className="mt-3 space-y-2">
          {stats.skillMastery.map((s) => (
            <div key={s.skill} className="card-paper flex items-center justify-between rounded-2xl px-4 py-3.5 transition-transform duration-300 hover:-translate-y-0.5">
              <span className="text-[15px] font-bold">{s.skill}</span>
              <span
                className={`rounded-full px-3 py-1 text-xs font-black ${
                  s.level === "Strong" ? "bg-rally-mist text-rally-deep ring-1 ring-rally/25" : s.level === "Improving" ? "bg-amber-soft text-amber-deep ring-1 ring-amber/30" : "bg-parchment-deep text-ink-soft ring-1 ring-ink/10"
                }`}
              >
                {s.level}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* trends */}
      {(stats.pronunciationTrend || stats.fluencyTrend) && (
        <section className="mt-8">
          <h2 className="font-display text-xl font-bold">Trends</h2>
          <div className="mt-3 space-y-2 rounded-2xl bg-white p-4 text-sm text-ink-soft shadow-[0_4px_18px_rgba(34,39,31,0.06)]">
            {stats.pronunciationTrend && <p>· {stats.pronunciationTrend}</p>}
            {stats.fluencyTrend && <p>· {stats.fluencyTrend}</p>}
          </div>
        </section>
      )}

      {/* competitive record — separate */}
      <section className="mt-6">
        <h2 className="px-1 font-display text-xl font-black">Debate record</h2>
        <p className="mt-1 px-1 text-xs font-medium text-ink-soft">Wins and losses are separate from learning progress.</p>
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-3 grid grid-cols-3 gap-2.5 text-center">
          <div className="card-paper rounded-2xl p-4">
            <p className="font-display text-[1.7rem] font-black text-rally tabular-nums">{record.wins}</p>
            <p className="text-[11px] font-bold uppercase tracking-widest text-ink-soft">Wins</p>
          </div>
          <div className="card-paper rounded-2xl p-4">
            <p className="font-display text-[1.7rem] font-black text-coral tabular-nums">{record.losses}</p>
            <p className="text-[11px] font-bold uppercase tracking-widest text-ink-soft">Losses</p>
          </div>
          <div className="card-paper rounded-2xl p-4">
            <p className="font-display text-[1.7rem] font-black tabular-nums">{record.draws}</p>
            <p className="text-[11px] font-bold uppercase tracking-widest text-ink-soft">Draws</p>
          </div>
        </motion.div>
      </section>

      {/* streak week */}
      <section className="mt-6">
        <h2 className="px-1 font-display text-xl font-black">This week</h2>
        <div className="card-paper mt-3 flex justify-between rounded-[1.4rem] p-4" aria-label="Last 7 days">
          {["M", "T", "W", "T", "F", "S", "S"].map((d, i) => (
            <div key={i} className="flex flex-col items-center gap-1.5">
              <span className={`flex h-9 w-9 items-center justify-center rounded-full text-sm font-black tabular-nums ${stats.streakHistory[i] ? "bg-gradient-to-b from-[#f5c15d] to-amber text-ink shadow-[0_6px_16px_-6px_rgba(232,155,46,0.8)]" : "bg-ink/8 text-ink-faint"}`}>
                {stats.streakHistory[i] ? "◆" : "·"}
              </span>
              <span className="text-[10px] font-bold text-ink-soft">{d}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-6 rounded-[1.4rem] border border-rally/20 bg-gradient-to-br from-[#eef7f1] to-rally-mist p-4 text-sm font-medium text-rally-deep shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]">
        Next up · <strong className="font-black">{current?.name}</strong> — {current?.description}
      </section>

      <TabBar />
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-white p-4 shadow-[0_4px_18px_rgba(34,39,31,0.06)]">
      <p className="font-display text-lg font-extrabold">{value}</p>
      <p className="text-xs text-ink-soft">{label}</p>
    </div>
  );
}
