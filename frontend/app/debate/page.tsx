"use client";

// Normal debate route: briefing → debate → results.
// Renders whatever setup the service provides; no topic logic here.

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { Button } from "@/components/shared/Button";
import { DebateFlow } from "@/components/debate/DebateFlow";
import { appService } from "@/lib/api";
import { useStore } from "@/lib/state/store";
import type { DebateReview, DebateSession, DebateSetup } from "@/lib/types";

export default function DebatePage() {
  return (
    <Suspense>
      <DebateLoader />
    </Suspense>
  );
}

function DebateLoader() {
  const params = useSearchParams();
  const router = useRouter();
  const topicId = params.get("topic");
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<{ session: DebateSession; setup: DebateSetup } | null>(null);
  const [briefed, setBriefed] = useState(false);
  const [side, setSide] = useState<"agree" | "disagree" | null>(null);

  async function begin(s: "agree" | "disagree") {
    try {
      setSide(s);
      const sess = await appService.startDebate({ topicId: topicId ?? undefined, side: s });
      setSession(sess);
      setBriefed(true);
    } catch {
      setError("Couldn't start this debate. Check your connection and try again.");
    }
  }

  function finish(review: DebateReview) {
    useStore.getState().applyReview(review);
    router.replace("/results");
  }

  if (!briefed || !session) return <Briefing topicId={topicId} error={error} side={side} onStart={begin} />;
  return <DebateFlow session={session.session} setup={session.setup} onFinish={finish} />;
}

function Briefing({ topicId, error, side, onStart }: { topicId: string | null; error: string | null; side: "agree" | "disagree" | null; onStart: (s: "agree" | "disagree") => void }) {
  const [info, setInfo] = useState<{ topic: string; skill: string; difficulty: string; turns: number; minutes: number; reminder: string } | null>(null);
  const router = useRouter();

  useEffect(() => {
    appService.getDebateChoices().then((topics) => {
      const t = topics.find((x) => x.id === topicId) ?? topics[0];
      setInfo({ topic: t.topic, skill: t.skill.replace(/_/g, " "), difficulty: t.difficulty, turns: t.turns, minutes: t.minutes, reminder: t.reminder });
    });
  }, [topicId]);

  if (!info) return <main className="flex min-h-dvh items-center justify-center text-ink-soft">Loading debate…</main>;

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col px-6 py-8">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="flex flex-1 flex-col">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">Briefing</p>
        <h1 className="mt-2 font-display text-3xl font-extrabold leading-tight tracking-tight">{info.topic}</h1>

        <dl className="mt-8 space-y-3 text-sm">
          <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
            <dt className="text-ink-soft">Skill target</dt>
            <dd className="font-semibold capitalize">{info.skill}</dd>
          </div>
          <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
            <dt className="text-ink-soft">Difficulty</dt>
            <dd className="font-semibold capitalize">{info.difficulty}</dd>
          </div>
          <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
            <dt className="text-ink-soft">Your turns</dt>
            <dd className="font-semibold">{info.turns}</dd>
          </div>
          <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
            <dt className="text-ink-soft">Estimated time</dt>
            <dd className="font-semibold">~{info.minutes} min</dd>
          </div>
        </dl>

        <p className="mt-6 rounded-2xl bg-rally-mist px-4 py-3 text-sm text-rally-deep">{info.reminder}</p>

        <p className="mt-8 font-semibold">Choose your side.</p>
        <div className="mt-2 flex gap-3">
          <button onClick={() => onStart("agree")} aria-pressed={side === "agree"} className={`flex-1 rounded-full border-2 py-3 font-semibold transition-colors ${side === "agree" ? "border-rally bg-rally-mist text-rally-deep" : "border-ink/10 bg-white"}`}>
            Agree
          </button>
          <button onClick={() => onStart("disagree")} aria-pressed={side === "disagree"} className={`flex-1 rounded-full border-2 py-3 font-semibold transition-colors ${side === "disagree" ? "border-coral bg-coral-soft text-coral" : "border-ink/10 bg-white"}`}>
            Disagree
          </button>
        </div>

        {error && (
          <p role="alert" className="mt-4 rounded-2xl bg-coral-soft px-4 py-3 text-sm font-medium text-coral">
            {error}
          </p>
        )}

        <div className="mt-auto flex items-center justify-between pt-10">
          <button onClick={() => router.back()} className="text-sm font-medium text-ink-soft underline underline-offset-4">
            Back
          </button>
          <Button onClick={() => onStart(side ?? "agree")} className="min-w-40">
            Start Debate
          </Button>
        </div>
      </motion.div>
    </main>
  );
}
