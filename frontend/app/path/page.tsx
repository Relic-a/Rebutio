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
    <main className="mx-auto min-h-dvh w-full max-w-md px-5 pb-28 pt-6">
      <header className="text-center">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">Your path</p>
        <h1 className="font-display text-2xl font-extrabold">
          {path.levelName} · Level {path.levelNumber}
        </h1>
      </header>

      <div className="relative mt-8">
        {/* connecting line */}
        <div className="absolute left-1/2 top-0 h-full w-0.5 -translate-x-1/2 bg-ink/10" aria-hidden />
        <ol className="space-y-5">
          {nodes.map((n, i) => (
            <motion.li
              key={n.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
              className={`relative flex ${i % 2 === 0 ? "justify-start" : "justify-end"}`}
            >
              <div
                className={`w-[72%] rounded-3xl p-4 ${
                  n.status === "current"
                    ? "bg-rally text-white shadow-[0_8px_24px_rgba(18,122,99,0.3)]"
                    : n.status === "complete"
                      ? "bg-white shadow-[0_4px_18px_rgba(34,39,31,0.06)]"
                      : "bg-white/60"
                }`}
                aria-current={n.status === "current" ? "step" : undefined}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className={`font-display font-bold ${n.status === "locked" ? "text-ink-soft" : ""}`}>{n.name}</p>
                    <p className={`mt-0.5 text-xs ${n.status === "current" ? "text-white/80" : "text-ink-soft"}`}>{n.description}</p>
                  </div>
                  <span
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold ${
                      n.status === "current" ? "bg-white/20 text-white" : n.status === "complete" ? "bg-rally-mist text-rally-deep" : "bg-ink/10 text-ink-soft"
                    }`}
                    aria-label={n.status === "locked" ? "Locked" : `Level ${n.order}`}
                  >
                    {n.status === "locked" ? "🔒" : n.order}
                  </span>
                </div>
                <div className="mt-2 flex items-center justify-between">
                  {n.status === "locked" ? (
                    <p className="text-xs text-ink-soft">Unlocks with 1★ on the previous skill</p>
                  ) : n.topicPreview ? (
                    <p className={`text-xs ${n.status === "current" ? "text-white/80" : "text-ink-soft"}`}>“{n.topicPreview}”</p>
                  ) : (
                    <span />
                  )}
                  {n.status !== "locked" && <StarRow stars={n.stars} size="sm" />}
                </div>
                {n.status === "current" && (
                  <Link
                    href={n.topicId ? `/debate?topic=${encodeURIComponent(n.topicId)}` : "/debate"}
                    className="mt-3 block rounded-full bg-white py-2.5 text-center text-sm font-semibold text-rally-deep"
                  >
                    Debate now
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
