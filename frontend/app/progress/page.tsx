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
    <main className="mx-auto min-h-dvh w-full max-w-md px-5 pb-28 pt-6">
      <h1 className="font-display text-3xl font-extrabold tracking-tight">Progress</h1>

      {/* top line: level / stars / streak / xp */}
      <div className="mt-6 grid grid-cols-2 gap-3 text-center">
        <Stat label="Path level" value={`${mockLearningPath.levelName} ${mockLearningPath.levelNumber}`} />
        <Stat label="Streak" value={`🔥 ${stats.streakDays} days`} />
        <Stat label="XP" value={merged.xp.toLocaleString()} />
        <Stat label="Debates" value={String(merged.debatesCompleted)} />
      </div>

      {/* learning progress */}
      <section className="mt-8">
        <h2 className="font-display text-xl font-bold">Speaking</h2>
        <div className="mt-3 space-y-2">
          {stats.skillMastery.map((s) => (
            <div key={s.skill} className="flex items-center justify-between rounded-2xl bg-white px-4 py-3 shadow-[0_4px_18px_rgba(34,39,31,0.06)]">
              <span className="font-medium">{s.skill}</span>
              <span
                className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  s.level === "Strong" ? "bg-rally-mist text-rally-deep" : s.level === "Improving" ? "bg-amber-soft text-amber-900" : "bg-parchment-deep text-ink-soft"
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
      <section className="mt-8">
        <h2 className="font-display text-xl font-bold">Debate record</h2>
        <p className="mt-1 text-xs text-ink-soft">Wins and losses are separate from learning progress.</p>
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-3 grid grid-cols-3 gap-3 text-center">
          <div className="rounded-2xl bg-white p-4 shadow-[0_4px_18px_rgba(34,39,31,0.06)]">
            <p className="font-display text-2xl font-extrabold text-rally">{record.wins}</p>
            <p className="text-xs text-ink-soft">Wins</p>
          </div>
          <div className="rounded-2xl bg-white p-4 shadow-[0_4px_18px_rgba(34,39,31,0.06)]">
            <p className="font-display text-2xl font-extrabold text-coral">{record.losses}</p>
            <p className="text-xs text-ink-soft">Losses</p>
          </div>
          <div className="rounded-2xl bg-white p-4 shadow-[0_4px_18px_rgba(34,39,31,0.06)]">
            <p className="font-display text-2xl font-extrabold">{record.draws}</p>
            <p className="text-xs text-ink-soft">Draws</p>
          </div>
        </motion.div>
      </section>

      {/* streak week */}
      <section className="mt-8">
        <h2 className="font-display text-xl font-bold">This week</h2>
        <div className="mt-3 flex justify-between rounded-2xl bg-white p-4 shadow-[0_4px_18px_rgba(34,39,31,0.06)]" aria-label="Last 7 days">
          {["M", "T", "W", "T", "F", "S", "S"].map((d, i) => (
            <div key={i} className="flex flex-col items-center gap-1.5">
              <span className={`flex h-8 w-8 items-center justify-center rounded-full text-sm ${stats.streakHistory[i] ? "bg-amber text-white" : "bg-ink/10 text-ink-soft"}`}>
                {stats.streakHistory[i] ? "🔥" : "·"}
              </span>
              <span className="text-[10px] text-ink-soft">{d}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-8 rounded-2xl bg-rally-mist p-4 text-sm text-rally-deep">
        Next up: <strong>{current?.name}</strong> — {current?.description}
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
