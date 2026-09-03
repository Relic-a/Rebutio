"use client";

// Debate Path: skill sequence with stars. One star on a node unlocks
// the next; higher stars are optional mastery. Locked ≠ punished.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { StarRow } from "@/components/shared/StarRow";
import { TabBar } from "@/components/shared/TabBar";
import { appService } from "@/lib/api";
import { getEffectivePath } from "@/lib/mock/fixtures";
import { useStore } from "@/lib/state/store";
import type { LearningPath } from "@/lib/types";

export default function PathPage() {
  const router = useRouter();
  const onboarded = useStore((s) => s.onboarded);
  const starsByNodeId = useStore((s) => s.starsByNodeId);
  const [livePath, setLivePath] = useState<LearningPath | null>(null);

  useEffect(() => {
    if (!onboarded) {
      appService.getAppBootstrap().then((b) => {
        if (!b.onboarded) router.replace("/onboarding");
      }).catch(() => router.replace("/onboarding"));
    }
    appService.getLearningPath().then((p) => setLivePath(p)).catch(() => {});
  }, [onboarded, router]);

  if (!onboarded) return <main className="flex min-h-dvh items-center justify-center" />;

  const path = livePath || getEffectivePath(starsByNodeId);
  const nodes = path.nodes;

  return (
    <main className="mx-auto min-h-dvh w-full max-w-md px-4 pb-32 pt-6">
      <header className="card-shell-dark">
        <div className="card-core arena-panel relative overflow-hidden px-5 py-6 text-center text-white">
          <div className="pointer-events-none absolute -left-10 -top-12 h-40 w-40 rounded-full bg-amber/25 blur-3xl" aria-hidden />
          <p className="relative text-[10px] font-bold uppercase tracking-[0.2em] text-white/60">Your path</p>
          <h1 className="relative mt-1 font-display text-[1.7rem] font-black leading-tight">
            {path.levelName} · <span className="tabular-nums">Level {path.levelNumber}</span>
          </h1>
          <div className="relative mx-auto mt-4 h-2 max-w-[240px] overflow-hidden rounded-full bg-white/15">
            <div
              className="h-full rounded-full bg-gradient-to-r from-amber via-[#ffe9bd] to-emerald-300"
              style={{ width: `${Math.round((nodes.filter((n) => n.status === "complete").length / Math.max(nodes.length, 1)) * 100)}%` }}
            />
          </div>
          <p className="relative mt-2 text-[11px] font-semibold text-white/65 tabular-nums">
            {nodes.filter((n) => n.status === "complete").length} of {nodes.length} skills sparred
          </p>
        </div>
      </header>

      <div className="relative mt-8">
        {/* connecting line */}
        <div className="absolute left-1/2 top-0 h-full w-0.5 -translate-x-1/2 bg-gradient-to-b from-rally/40 via-ink/10 to-transparent" aria-hidden />
        <ol className="space-y-5">
          {nodes.map((n, i) => (
            <motion.li
              key={n.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04, type: "spring", stiffness: 260, damping: 28 }}
              className={`relative flex ${i % 2 === 0 ? "justify-start" : "justify-end"}`}
            >
              <div
                className={`w-[74%] rounded-[1.4rem] p-4 transition-transform duration-300 ${
                  n.status === "current"
                    ? "bg-gradient-to-br from-rally to-rally-deep text-white shadow-[0_20px_40px_-16px_rgba(14,122,95,0.6),inset_0_1px_0_rgba(255,255,255,0.25)] ring-1 ring-white/20"
                    : n.status === "complete"
                      ? "card-paper"
                      : "rounded-[1.4rem] border border-dashed border-ink/15 bg-white/55 backdrop-blur-sm"
                }`}
                aria-current={n.status === "current" ? "step" : undefined}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className={`font-display text-[15px] font-black leading-tight ${n.status === "locked" ? "text-ink-soft" : ""}`}>{n.name}</p>
                    <p className={`mt-0.5 line-clamp-2 text-xs leading-snug ${n.status === "current" ? "text-white/80" : "text-ink-soft"}`}>{n.description}</p>
                  </div>
                  <span
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-black tabular-nums ${
                      n.status === "current"
                        ? "bg-white text-rally-deep shadow"
                        : n.status === "complete"
                          ? "bg-rally-mist text-rally-deep ring-1 ring-rally/20"
                          : "bg-ink/8 text-ink-soft"
                    }`}
                    aria-label={n.status === "locked" ? "Locked" : `Level ${n.order}`}
                  >
                    {n.status === "locked" ? (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden>
                        <rect x="4" y="11" width="16" height="10" rx="2.5" />
                        <path d="M8 11V7a4 4 0 0 1 8 0v4" />
                      </svg>
                    ) : (
                      n.order
                    )}
                  </span>
                </div>
                <div className="mt-2.5 flex items-center justify-between gap-2">
                  {n.status === "locked" ? (
                    <p className="text-[11px] font-medium text-ink-soft">Unlocks with 1 star above</p>
                  ) : n.topicPreview ? (
                    <p className={`truncate text-xs font-medium ${n.status === "current" ? "text-white/85" : "text-ink-soft"}`}>“{n.topicPreview}”</p>
                  ) : (
                    <span />
                  )}
                  {n.status !== "locked" && <StarRow stars={n.stars} size="sm" />}
                </div>
                {n.status === "current" && (
                  <Link
                    href={n.topicId ? `/debate?topic=${encodeURIComponent(n.topicId)}` : "/debate"}
                    className="mt-3 flex items-center justify-center gap-2 rounded-full bg-white py-2.5 text-center text-sm font-black text-rally-deep transition-all hover:bg-[#ffe9bd] active:scale-[0.98]"
                  >
                    Debate now <span aria-hidden>→</span>
                  </Link>
                )}
              </div>
            </motion.li>
          ))}
        </ol>
      </div>

      <TabBar />
    </main>
  );
}
