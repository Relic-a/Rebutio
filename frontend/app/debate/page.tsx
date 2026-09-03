"use client";

// Normal debate route: briefing → debate → results.
// Enforces progression lock: locked nodes cannot be accessed by URL tampering.

import { Suspense, useEffect, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { Button } from "@/components/shared/Button";
import { ContinuousDebateFlow } from "@/components/debate/ContinuousDebateFlow";
import { appService } from "@/lib/api";
import { getEffectivePath, mockDebateTopics } from "@/lib/mock/fixtures";
import { useStore } from "@/lib/state/store";
import type { DebateReview, DebateSession, DebateSetup, PathNode } from "@/lib/types";

export default function DebatePage() {
  return (
    <Suspense>
      <DebateLoader />
    </Suspense>
  );
}

function DebateLoader() {
  const params = useSearchParams();
  const routeParams = useParams();
  const router = useRouter();

  const routeId = routeParams?.id as string | undefined;
  const targetParam =
    routeId ||
    params.get("topic") ||
    params.get("level") ||
    params.get("step") ||
    params.get("order") ||
    params.get("skill") ||
    null;

  const sessionId = params.get("sessionId");
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<{ session: DebateSession; setup: DebateSetup } | null>(null);
  const [briefed, setBriefed] = useState(false);
  const [side, setSide] = useState<"agree" | "disagree" | null>(null);
  const [starting, setStarting] = useState(false);
  const startInFlight = useRef(false);

  useEffect(() => {
    if (sessionId && !session && !startInFlight.current) {
      startInFlight.current = true;
      setStarting(true);
      appService.getSession(sessionId).then((existingSession) => {
        const setup: DebateSetup = {
          topic: existingSession.topic,
          skillTarget: existingSession.skillTarget,
          skillReminder: existingSession.skillReminder,
          difficulty: existingSession.difficulty,
          totalUserTurns: existingSession.totalUserTurns,
          secondsPerTurn: 0,
          opponentLines: [],
        };
        setSession({ session: existingSession, setup });
        setBriefed(true);
      }).catch(() => {
        setError("Could not resume debate session. You can start a new debate below.");
      }).finally(() => {
        startInFlight.current = false;
        setStarting(false);
      });
    }
  }, [sessionId, session]);

  async function begin(s: "agree" | "disagree", topicToStart?: string) {
    if (startInFlight.current) return;
    startInFlight.current = true;
    try {
      setSide(s);
      setStarting(true);
      setError(null);
      const chosenTopicId = topicToStart ?? targetParam ?? undefined;
      const sess = await appService.startDebate({ topicId: chosenTopicId, side: s });
      setSession(sess);
      setBriefed(true);
    } catch (err: any) {
      const msg = err?.message || err?.detail || "Couldn't start this debate. Check your connection and try again.";
      setError(msg);
    } finally {
      startInFlight.current = false;
      setStarting(false);
    }
  }

  function finish(review: DebateReview, turns?: Array<{ speaker: string; text: string }>) {
    useStore.getState().applyReview(review, { turns });
    router.replace("/results");
  }

  if (!briefed || !session) {
    return (
      <Briefing
        targetParam={targetParam}
        error={error}
        side={side}
        starting={starting}
        onSelectSide={setSide}
        onStart={begin}
      />
    );
  }
  return <ContinuousDebateFlow session={session.session} setup={session.setup} onFinish={finish} />;
}

function Briefing({
  targetParam,
  error,
  side,
  starting,
  onSelectSide,
  onStart,
}: {
  targetParam: string | null;
  error: string | null;
  side: "agree" | "disagree" | null;
  starting: boolean;
  onSelectSide: (side: "agree" | "disagree") => void;
  onStart: (side: "agree" | "disagree", topicToStart?: string) => void;
}) {
  const [info, setInfo] = useState<{
    topicId: string;
    topic: string;
    skill: string;
    difficulty: string;
    turns: number;
    minutes: number;
    reminder: string;
    order: number;
  } | null>(null);
  const [lockedInfo, setLockedInfo] = useState<{
    order: number;
    name: string;
    description: string;
    prevName?: string;
    prevOrder?: number;
  } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const starsByNodeId = useStore.getState().starsByNodeId;
        const [path, choices] = await Promise.all([
          appService.getLearningPath().catch(() => getEffectivePath(starsByNodeId)),
          appService.getDebateChoices().catch(() => mockDebateTopics),
        ]);

        if (cancelled) return;

        let targetNode: PathNode | undefined;
        if (targetParam) {
          const trimmed = targetParam.trim().toLowerCase();
          // 1. Check numeric order or prefixed order like "level-2", "debate-2"
          const numMatch = trimmed.match(/^(?:level[-_]?|debate[-_]?|step[-_]?)?(\d+)$/);
          if (numMatch) {
            const order = parseInt(numMatch[1], 10);
            targetNode = path.nodes.find((n) => n.order === order);
          }
          // 2. Check by node id
          if (!targetNode) {
            targetNode = path.nodes.find((n) => n.id.toLowerCase() === trimmed);
          }
          // 3. Check by topicId on node
          if (!targetNode) {
            targetNode = path.nodes.find((n) => n.topicId && n.topicId.toLowerCase() === trimmed);
          }
          // 4. Check by topic in choices or mockDebateTopics
          if (!targetNode) {
            const matchedTopic =
              choices.find((c) => c.id.toLowerCase() === trimmed) ||
              mockDebateTopics.find((t) => t.id.toLowerCase() === trimmed);
            if (matchedTopic) {
              targetNode = path.nodes.find((n) => n.id === matchedTopic.skill);
            }
          }
        }

        // Default to current node or first node if no target was found
        if (!targetNode) {
          if (targetParam) {
            setLoadError("This debate level or topic is not found. Return to your path to pick an available debate.");
            return;
          }
          targetNode = path.nodes.find((n) => n.status === "current") || path.nodes[0];
        }

        // Progression lock check: block locked nodes strictly
        if (targetNode.status === "locked") {
          const prevNode = path.nodes.find((n) => n.order === targetNode!.order - 1);
          setLockedInfo({
            order: targetNode.order,
            name: targetNode.name,
            description: targetNode.description,
            prevName: prevNode?.name,
            prevOrder: prevNode?.order,
          });
          return;
        }

        // Unlocked: load topic information
        const topicChoice = choices.find((c) => c.skill === targetNode!.id || c.id === targetNode!.topicId);
        const mockFallback = mockDebateTopics.find((t) => t.skill === targetNode!.id || t.id === targetNode!.topicId);

        const topicText = targetNode.topicPreview || topicChoice?.topic || mockFallback?.topic || "State your claim and defend it.";
        const reminderText = topicChoice?.reminder || mockFallback?.reminder || `Focus on ${targetNode.name}.`;
        const difficulty = topicChoice?.difficulty || mockFallback?.difficulty || "gentle";
        const turns = topicChoice?.turns || mockFallback?.turns || 4;
        const minutes = topicChoice?.minutes || mockFallback?.minutes || 5;

        setInfo({
          topicId: targetNode.topicId || targetNode.id,
          topic: topicText,
          skill: targetNode.name,
          difficulty,
          turns,
          minutes,
          reminder: reminderText,
          order: targetNode.order,
        });
      } catch {
        if (!cancelled) {
          setLoadError("Couldn't load this debate. Check your connection and try again.");
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [targetParam]);

  if (lockedInfo) {
    return (
      <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center px-6 py-8">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="rounded-3xl bg-white p-6 text-center shadow-[0_8px_30px_rgba(34,39,31,0.08)]"
        >
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-ink/5 text-3xl">
            🔒
          </div>
          <p className="mt-4 text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">
            Level {lockedInfo.order} · Locked
          </p>
          <h1 className="mt-1 font-display text-2xl font-extrabold text-ink">
            {lockedInfo.name}
          </h1>
          <p className="mt-3 text-sm text-ink-soft leading-relaxed">
            {lockedInfo.prevName ? (
              <>
                This debate is locked. Earn at least <strong className="text-amber-800">1★</strong> on{" "}
                <strong className="text-ink font-semibold">{lockedInfo.prevName}</strong> (Level {lockedInfo.prevOrder}) to unlock it.
              </>
            ) : (
              "This debate is locked. Complete the previous level on your path to unlock it."
            )}
          </p>
          <div className="mt-6 flex flex-col gap-3">
            <Button onClick={() => router.push("/path")} className="w-full">
              View Your Path
            </Button>
            <button
              onClick={() => router.push("/debate")}
              className="text-sm font-semibold text-ink-soft hover:text-ink transition-colors py-2"
            >
              Go to Current Unlocked Debate
            </button>
          </div>
        </motion.div>
      </main>
    );
  }

  if (loadError) {
    return (
      <main className="flex min-h-dvh items-center justify-center px-6">
        <div className="max-w-sm text-center">
          <p role="alert" className="text-sm text-coral">{loadError}</p>
          <Button onClick={() => router.push("/path")} className="mt-5">Back to path</Button>
        </div>
      </main>
    );
  }

  if (!info) return <main className="flex min-h-dvh items-center justify-center text-ink-soft">Loading debate…</main>;

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col px-6 py-8">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="flex flex-1 flex-col">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">Briefing</p>
          <span className="rounded-full bg-ink/5 px-2.5 py-0.5 text-xs font-semibold text-ink-soft">
            Level {info.order}
          </span>
        </div>
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
            <dt className="text-ink-soft">Format</dt>
            <dd className="font-semibold">Continuous Spoken Spar</dd>
          </div>
          <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3">
            <dt className="text-ink-soft">Estimated time</dt>
            <dd className="font-semibold">~{info.minutes || 3} min</dd>
          </div>
        </dl>

        <p className="mt-6 rounded-2xl bg-rally-mist px-4 py-3 text-sm text-rally-deep">{info.reminder}</p>

        <p className="mt-8 font-semibold">Choose your side.</p>
        <div className="mt-2 flex gap-3">
          <button
            disabled={starting}
            onClick={() => onSelectSide("agree")}
            aria-pressed={side === "agree"}
            className={`flex-1 rounded-full border-2 py-3 font-semibold transition-colors disabled:cursor-not-allowed ${side === "agree" ? "border-rally bg-rally-mist text-rally-deep" : "border-ink/10 bg-white"}`}
          >
            Agree
          </button>
          <button
            disabled={starting}
            onClick={() => onSelectSide("disagree")}
            aria-pressed={side === "disagree"}
            className={`flex-1 rounded-full border-2 py-3 font-semibold transition-colors disabled:cursor-not-allowed ${side === "disagree" ? "border-coral bg-coral-soft text-coral" : "border-ink/10 bg-white"}`}
          >
            Disagree
          </button>
        </div>

        {error && (
          <p role="alert" className="mt-4 rounded-2xl bg-coral-soft px-4 py-3 text-sm font-medium text-coral">
            {error}
          </p>
        )}

        <div className="mt-auto flex items-center justify-between pt-10">
          <button onClick={() => router.push("/path")} className="text-sm font-medium text-ink-soft underline underline-offset-4">
            Back to path
          </button>
          <Button
            disabled={starting}
            onClick={() => onStart(side ?? "agree", info.topicId)}
            className="min-w-40"
          >
            {starting ? "Starting…" : "Start Debate"}
          </Button>
        </div>
      </motion.div>
    </main>
  );
}
