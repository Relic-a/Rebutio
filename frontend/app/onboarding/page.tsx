"use client";

// Onboarding: promise → goal → comfort → interests → intensity →
// spar briefing → mic permission → first mini-debate → placement result.
// No formal placement test; the first debate is the assessment.

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { Button } from "@/components/shared/Button";
import { Logo } from "@/components/shared/Logo";
import { ContinuousDebateFlow } from "@/components/debate/ContinuousDebateFlow";
import { appService } from "@/lib/api";
import { onboardingOptions } from "@/lib/mock/fixtures";
import { capture } from "@/lib/media/capture";
import { logger } from "@/lib/logger";
import { useStore } from "@/lib/state/store";
import type { DebateReview, DebateSession, DebateSetup } from "@/lib/types";

type Step = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9;

export default function OnboardingPage() {
  const router = useRouter();
  const completeOnboarding = useStore((s) => s.completeOnboarding);
  const [step, setStep] = useState<Step>(1);
  const [goals, setGoals] = useState<string[]>([]);
  const [comfort, setComfort] = useState("");
  const [interests, setInterests] = useState<string[]>([]);
  const [intensity, setIntensity] = useState<"easygoing" | "balanced" | "bring_it_on">("balanced");
  const [session, setSession] = useState<{ session: DebateSession; setup: DebateSetup } | null>(null);
  const [micState, setMicState] = useState<"prompt" | "allowed" | "denied" | "unavailable">("prompt");

  const [pendingSession, setPendingSession] = useState<{ session: DebateSession; setup: DebateSetup } | null>(null);

  const sparTopic = useMemo(() => {
    const key = interests.find((i) => onboardingOptions.interests.some((o) => o.id === i));
    const map: Record<string, string> = {
      tech: "Social media has made friendships worse.",
      relationships: "Social media has made friendships worse.",
      money: "Money can buy happiness.",
      psychology: "Money can buy happiness.",
      society: "Schools should ban phones entirely during the day.",
      careers: "The four-day work week should become standard.",
      gaming: "Video games are a legitimate competitive sport.",
      popculture: "AI-generated images should count as real art.",
      science: "Space exploration spending should go to problems on Earth.",
      ethics: "People should be allowed to use any name and identity online.",
      sports: "Video games are a legitimate competitive sport.",
      weird: "Cats are better pets than dogs.",
    };
    return map[key ?? "tech"];
  }, [interests]);

  function toggle<T extends string>(list: T[], v: T, set: (l: T[]) => void) {
    set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  }

  async function startSpar(side: "agree" | "disagree") {
    // Save preferences to backend and prepare session
    try {
      await appService.saveOnboardingPreferences({
        goals,
        comfort,
        interests,
        intensity,
      });
    } catch (e) {
      logger.warn("onboarding.persist_preferences_failed", { error: (e as any)?.message });
    }
    const s = await appService.startDebate({ side, onboarding: true, interests });
    setPendingSession(s);
    capture.checkAvailability().then((avail) => {
      if (avail === "available") {
        setSession(s);
        setStep(8);
      } else {
        setStep(7);
      }
    });
  }

  function continueToDebate() {
    if (pendingSession) {
      setSession(pendingSession);
      setStep(8);
    } else {
      setStep(8);
    }
  }

  async function requestMic() {
    const r = await capture.requestPermission();
    setMicState(r);
    if (r === "allowed") setStep(8);
  }

  function finish(review: DebateReview) {
    completeOnboarding({ goals, comfort, interests, intensity });
    // First spar is a placement debate — stars don't map onto a path node yet.
    useStore.getState().applyReview(review, { recordStars: false });
    router.replace("/results?first=1");
  }

  return (
    <main className="mx-auto min-h-dvh w-full max-w-md px-6 py-8">
      <AnimatePresence mode="wait">
        {step === 1 && <Welcome key="s1" onNext={() => setStep(2)} />}
        {step === 2 && (
          <ChoiceStep
            key="s2"
            title="What do you want to get better at?"
            sub="Pick up to 3."
            canContinue={goals.length >= 1}
            onBack={() => setStep(1)}
            onContinue={() => setStep(3)}
          >
            <div className="flex flex-col gap-3">
              {onboardingOptions.goals.map((g) => (
                <Chip key={g} selected={goals.includes(g)} onClick={() => goals.includes(g) || goals.length < 3 ? toggle(goals, g, setGoals) : null}>
                  {g}
                </Chip>
              ))}
            </div>
          </ChoiceStep>
        )}
        {step === 3 && (
          <ChoiceStep
            key="s3"
            title="How comfortable are you speaking English?"
            sub="This is just a starting hint — your first debate tells us more."
            canContinue={!!comfort}
            onBack={() => setStep(2)}
            onContinue={() => setStep(4)}
          >
            <div className="flex flex-col gap-3">
              {onboardingOptions.comfort.map((c) => (
                <Chip key={c} selected={comfort === c} onClick={() => setComfort(c)}>
                  {c}
                </Chip>
              ))}
            </div>
          </ChoiceStep>
        )}
        {step === 4 && (
          <ChoiceStep
            key="s4"
            title="What could you argue about for hours?"
            sub="Pick at least 3 — debates will come from here."
            canContinue={interests.length >= 3}
            onBack={() => setStep(3)}
            onContinue={() => setStep(5)}
          >
            <div className="grid grid-cols-2 gap-3">
              {onboardingOptions.interests.map((i) => (
                <button
                  key={i.id}
                  onClick={() => toggle(interests, i.id, setInterests)}
                  aria-pressed={interests.includes(i.id)}
                  className={`flex min-h-24 flex-col items-center justify-center gap-1 rounded-3xl border-2 p-3 text-center text-sm font-semibold transition-all ${
                    interests.includes(i.id) ? "border-rally bg-rally-mist text-rally-deep" : "border-ink/10 bg-white text-ink-soft"
                  }`}
                >
                  <span className="text-2xl" aria-hidden>{i.emoji}</span>
                  {i.label}
                </button>
              ))}
            </div>
          </ChoiceStep>
        )}
        {step === 5 && (
          <ChoiceStep
            key="s5"
            title="How hard should Rebutio push back?"
            sub="This is debate intensity — not your level."
            canContinue
            onBack={() => setStep(4)}
            onContinue={() => setStep(6)}
          >
            <div className="flex flex-col gap-3">
              {onboardingOptions.intensity.map((i) => (
                <button
                  key={i.id}
                  onClick={() => setIntensity(i.id)}
                  aria-pressed={intensity === i.id}
                  className={`rounded-3xl border-2 p-5 text-left transition-all ${
                    intensity === i.id ? "border-rally bg-rally-mist" : "border-ink/10 bg-white"
                  }`}
                >
                  <p className="font-display text-lg font-bold">{i.name}</p>
                  <p className="mt-1 text-sm text-ink-soft">{i.blurb}</p>
                </button>
              ))}
            </div>
          </ChoiceStep>
        )}
        {step === 6 && <SparBriefing key="s6" topic={sparTopic} onBack={() => setStep(5)} onStart={startSpar} />}
        {step === 7 && <MicPermission key="s7" state={micState} onEnable={async () => { const r = await capture.requestPermission(); setMicState(r); continueToDebate(); }} onSkip={continueToDebate} onRetry={async () => { const r = await capture.requestPermission(); setMicState(r); if (r === "allowed") continueToDebate(); }} />}
        {step === 8 && session && <ContinuousDebateFlow key="s8" session={session.session} setup={session.setup} onFinish={finish} />}
        {step === 9 && <div />}
      </AnimatePresence>
    </main>
  );
}

function Welcome({ onNext }: { onNext: () => void }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex min-h-[85dvh] flex-col">
      <Logo size={36} />
      <div className="mt-10">
        <span className="eyebrow bg-ink text-[#ffe9bd]">Live spoken sparring</span>
        <h1 className="mt-4 font-display text-[2.6rem] font-black leading-[1.02] tracking-tight">
          Speak English like you already <span className="bg-gradient-to-r from-rally via-emerald-500 to-amber bg-clip-text text-transparent">think</span> in it.
        </h1>
        <p className="mt-4 max-w-[30ch] text-[17px] leading-relaxed text-ink-soft">Defend ideas worth talking about. A coach listens, scores, and sharpens every turn.</p>
      </div>

      {/* miniature live debate preview */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25, type: "spring", stiffness: 220, damping: 26 }}
        className="card-shell mt-8"
      >
        <div className="card-core relative overflow-hidden bg-ink p-5 text-white">
          <div className="pointer-events-none absolute -right-10 -top-10 h-36 w-36 rounded-full bg-rally/50 blur-2xl" aria-hidden />
          <div className="relative flex items-center justify-between">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-white/60">Today&apos;s spar</p>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-2.5 py-1 text-[10px] font-bold text-emerald-200 ring-1 ring-white/15">
              <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-emerald-300" />
              Live
            </span>
          </div>
          <p className="relative mt-2 font-display text-[1.45rem] font-black leading-snug">College is overrated.</p>
          <div className="relative mt-4 flex gap-2.5">
            <span className="flex-1 rounded-full bg-[#e8f5ee] py-2.5 text-center text-sm font-black text-rally-deep">Agree</span>
            <span className="flex-1 rounded-full bg-[#ffe9e3] py-2.5 text-center text-sm font-black text-coral-deep">Disagree</span>
          </div>
        </div>
      </motion.div>

      <div className="mt-auto pt-10">
        <Button onClick={onNext} className="w-full text-lg">
          Start my first debate
          <span aria-hidden>→</span>
        </Button>
        <p className="mt-4 text-center text-xs font-medium text-ink-soft">Live spoken spar · No grammar drills · Just argue</p>
      </div>
    </motion.div>
  );
}

function ChoiceStep({
  title,
  sub,
  children,
  canContinue,
  onBack,
  onContinue,
}: {
  title: string;
  sub?: string;
  children: React.ReactNode;
  canContinue: boolean;
  onBack: () => void;
  onContinue: () => void;
}) {
  return (
    <motion.div initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }} transition={{ type: "spring", stiffness: 260, damping: 30 }} className="flex min-h-[85dvh] flex-col">
      <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-rally">Step forward</p>
      <h1 className="mt-1.5 font-display text-[2rem] font-black leading-[1.05] tracking-tight">{title}</h1>
      {sub && <p className="mt-2 text-sm font-medium text-ink-soft">{sub}</p>}
      <div className="mt-8 flex-1">{children}</div>
      <div className="flex items-center gap-4 pt-8">
        <button onClick={onBack} className="rounded-full px-4 py-3 text-sm font-bold text-ink-soft transition-colors hover:bg-ink/5 hover:text-ink">
          ← Back
        </button>
        <Button onClick={onContinue} disabled={!canContinue} className="ml-auto min-w-40">
          Continue →
        </Button>
      </div>
    </motion.div>
  );
}

function Chip({ children, selected, onClick }: { children: React.ReactNode; selected: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={selected}
      className={`group flex items-center justify-between gap-3 rounded-2xl border px-5 py-4 text-left font-bold transition-all duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] active:scale-[0.98] ${
        selected
          ? "border-rally bg-gradient-to-b from-[#eef7f1] to-rally-mist text-rally-deep shadow-[0_10px_24px_-12px_rgba(14,122,95,0.5),inset_0_1px_0_rgba(255,255,255,0.8)]"
          : "hairline card-paper hover:-translate-y-0.5"
      }`}
    >
      <span>{children}</span>
      <span
        className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-black transition-all ${
          selected ? "bg-rally text-white" : "bg-ink/8 text-ink-faint group-hover:bg-ink/12"
        }`}
        aria-hidden
      >
        {selected ? "✓" : "+"}
      </span>
    </button>
  );
}

function SparBriefing({ topic, onBack, onStart }: { topic: string; onBack: () => void; onStart: (side: "agree" | "disagree") => void }) {
  const [side, setSide] = useState<"agree" | "disagree" | null>(null);
  const [loading, setLoading] = useState(false);
  return (
    <motion.div initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} className="flex min-h-[85dvh] flex-col">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">First spar</p>
      <h1 className="mt-1 font-display text-3xl font-extrabold tracking-tight">Let&apos;s see how you argue.</h1>
      <ul className="mt-4 space-y-1 text-sm text-ink-soft">
        <li>· Live continuous spar</li>
        <li>· No right answer</li>
        <li>· No pressure — this helps Rebutio choose where your path starts</li>
      </ul>

      <div className="mt-8 rounded-3xl bg-white p-5 shadow-[0_8px_30px_rgba(34,39,31,0.08)]">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-soft">The motion</p>
        <p className="mt-1 font-display text-2xl font-bold leading-snug">{topic}</p>
        <p className="mt-6 text-sm font-semibold text-ink">Pick a side.</p>
        <div className="mt-2 flex gap-3">
          <button onClick={() => setSide("agree")} aria-pressed={side === "agree"} className={`flex-1 rounded-full border-2 py-3 font-semibold transition-all ${side === "agree" ? "border-rally bg-rally-mist text-rally-deep" : "border-ink/10"}`}>
            Agree
          </button>
          <button onClick={() => setSide("disagree")} aria-pressed={side === "disagree"} className={`flex-1 rounded-full border-2 py-3 font-semibold transition-all ${side === "disagree" ? "border-coral bg-coral-soft text-coral" : "border-ink/10"}`}>
            Disagree
          </button>
        </div>
      </div>

      <div className="mt-auto flex items-center gap-4 pt-10">
        <button onClick={onBack} className="text-sm font-medium text-ink-soft underline underline-offset-4">
          Back
        </button>
        <Button
          onClick={async () => {
            if (!side) return;
            setLoading(true);
            await onStart(side);
            setLoading(false);
          }}
          disabled={!side || loading}
          className="ml-auto min-w-40"
        >
          {loading ? "Loading…" : "Start Spar"}
        </Button>
      </div>
    </motion.div>
  );
}

function MicPermission({ state, onEnable, onSkip, onRetry }: { state: string; onEnable: () => void; onSkip: () => void; onRetry: () => void }) {
  return (
    <motion.div initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} className="flex min-h-[85dvh] flex-col items-center justify-center text-center">
      <div className="flex h-24 w-24 items-center justify-center rounded-full bg-rally-mist text-4xl" aria-hidden>🎙️</div>
      <h1 className="mt-6 font-display text-3xl font-extrabold tracking-tight">Rebutio needs to hear your side.</h1>
      <p className="mt-3 text-ink-soft">Your voice is how you debate.</p>
      {state === "denied" && (
        <p role="alert" className="mt-6 rounded-2xl bg-coral-soft px-4 py-3 text-sm font-medium text-coral">
          Microphone access was blocked. Enable it in your browser settings, or continue without audio.
        </p>
      )}
      {state === "unavailable" && (
        <p role="alert" className="mt-6 rounded-2xl bg-amber-soft px-4 py-3 text-sm font-medium text-amber-900">
          No microphone found on this device. You can continue — turns will run without recording.
        </p>
      )}
      <div className="mt-8 flex w-full flex-col gap-3">
        {(state === "denied" || state === "unavailable") ? (
          <>
            <Button onClick={onRetry}>Try again</Button>
            <Button variant="secondary" onClick={onSkip}>Continue without audio</Button>
          </>
        ) : (
          <>
            <Button onClick={onEnable}>Enable microphone</Button>
            <Button variant="ghost" onClick={onSkip}>Not now</Button>
          </>
        )}
      </div>
    </motion.div>
  );
}
