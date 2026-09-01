"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { TabBar } from "@/components/shared/TabBar";
import { AuthModal } from "@/components/shared/AuthModal";
import { appService, insforge } from "@/lib/api";
import { onboardingOptions } from "@/lib/mock/fixtures";
import { useStore } from "@/lib/state/store";

export default function ProfilePage() {
  const router = useRouter();
  const onboarded = useStore((s) => s.onboarded);
  const preferences = useStore((s) => s.preferences);
  const reset = useStore((s) => s.reset);
  const [intensity, setIntensity] = useState(preferences.intensity);
  const [captions, setCaptions] = useState(true);
  const [saveTranscripts, setSaveTranscripts] = useState(false);
  const [saved, setSaved] = useState(false);
  const [authUser, setAuthUser] = useState<any>(null);
  const [showAuthModal, setShowAuthModal] = useState(false);

  useEffect(() => {
    // Check InsForge user session
    insforge.auth.getCurrentUser().then(({ data }) => {
      if (data?.user) setAuthUser(data.user);
    }).catch(() => {});

    const unsubscribe = insforge.auth.onAuthStateChange(() => {
      insforge.auth.getCurrentUser().then(({ data }) => {
        setAuthUser(data?.user ?? null);
      });
    });

    return () => unsubscribe();
  }, []);

  useEffect(() => {
    if (!onboarded) router.replace("/onboarding");
    appService
      .getSettings()
      .then((data) => {
        if (data) {
          if (data.saveTranscripts !== undefined) setSaveTranscripts(Boolean(data.saveTranscripts));
          if (data.captionsEnabled !== undefined) setCaptions(Boolean(data.captionsEnabled));
          if (data.intensity) setIntensity(data.intensity as typeof intensity);
        }
      })
      .catch(() => {});
  }, [onboarded, router]);

  async function updateSetting(patch: { saveTranscripts?: boolean; captionsEnabled?: boolean; intensity?: string }) {
    await appService.updateSettings(patch).catch(() => {});
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }

  function saveIntensity(v: typeof intensity) {
    setIntensity(v);
    useStore.setState({ preferences: { ...useStore.getState().preferences, intensity: v } });
    updateSetting({ intensity: v });
  }

  function toggleSaveTranscripts(val: boolean) {
    setSaveTranscripts(val);
    updateSetting({ saveTranscripts: val });
  }

  function toggleCaptions(val: boolean) {
    setCaptions(val);
    updateSetting({ captionsEnabled: val });
  }

  if (!onboarded) return <main className="flex min-h-dvh items-center justify-center" />;

  return (
    <main className="mx-auto min-h-dvh w-full max-w-md px-5 pb-28 pt-6">
      <h1 className="font-display text-3xl font-extrabold tracking-tight">Profile</h1>
      <p className="mt-1 text-sm text-ink-soft">Your debate settings and privacy preferences.</p>

      <section className="mt-8">
        <h2 className="font-display text-lg font-bold">Your goals</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          {preferences.goals.length > 0 ? (
            preferences.goals.map((g) => (
              <span key={g} className="rounded-full bg-rally-mist px-3.5 py-1.5 text-sm font-medium text-rally-deep">
                {g}
              </span>
            ))
          ) : (
            <span className="text-sm text-ink-soft">None selected yet.</span>
          )}
        </div>
      </section>

      <section className="mt-8">
        <h2 className="font-display text-lg font-bold">Debate interests</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          {preferences.interests.map((id) => {
            const i = onboardingOptions.interests.find((o) => o.id === id);
            return (
              <span key={id} className="rounded-full bg-white px-3.5 py-1.5 text-sm font-medium shadow-[0_2px_10px_rgba(34,39,31,0.06)]">
                {i?.emoji} {i?.label}
              </span>
            );
          })}
        </div>
      </section>

      <section className="mt-8">
        <h2 className="font-display text-lg font-bold">Opponent intensity</h2>
        <div className="mt-3 flex flex-col gap-2">
          {onboardingOptions.intensity.map((i) => (
            <button
              key={i.id}
              onClick={() => saveIntensity(i.id)}
              aria-pressed={intensity === i.id}
              className={`flex items-center justify-between rounded-2xl border-2 px-4 py-3 text-left transition-colors ${
                intensity === i.id ? "border-rally bg-rally-mist" : "border-ink/10 bg-white"
              }`}
            >
              <span>
                <span className="block font-semibold">{i.name}</span>
                <span className="block text-xs text-ink-soft">{i.blurb}</span>
              </span>
              {intensity === i.id && <span className="text-rally font-bold">✓</span>}
            </button>
          ))}
        </div>
      </section>

      <section className="mt-8">
        <h2 className="font-display text-lg font-bold">Privacy & Data</h2>
        <label className="mt-3 flex items-center justify-between rounded-2xl bg-white px-4 py-3 shadow-[0_2px_10px_rgba(34,39,31,0.04)]">
          <div>
            <span className="block text-sm font-medium">Save debate transcripts</span>
            <span className="block text-xs text-ink-soft">When off, debate speech text is wiped after review.</span>
          </div>
          <input
            type="checkbox"
            checked={saveTranscripts}
            onChange={(e) => toggleSaveTranscripts(e.target.checked)}
            className="h-5 w-5 accent-rally ml-4 shrink-0"
          />
        </label>
      </section>

      <section className="mt-8">
        <h2 className="font-display text-lg font-bold">Accessibility & audio</h2>
        <label className="mt-3 flex items-center justify-between rounded-2xl bg-white px-4 py-3 shadow-[0_2px_10px_rgba(34,39,31,0.04)]">
          <span className="text-sm font-medium">Show captions when available</span>
          <input
            type="checkbox"
            checked={captions}
            onChange={(e) => toggleCaptions(e.target.checked)}
            className="h-5 w-5 accent-rally"
          />
        </label>
        <p className="mt-2 px-1 text-xs text-ink-soft">Audio turns send raw voice evidence for analysis.</p>
      </section>

      <section className="mt-8">
        <h2 className="font-display text-lg font-bold">Account & Cloud Sync</h2>
        <div className="mt-3 rounded-2xl bg-white p-4 shadow-[0_2px_10px_rgba(34,39,31,0.04)]">
          {authUser ? (
            <div className="flex items-center justify-between">
              <div>
                <span className="block text-sm font-semibold text-ink">{authUser.email}</span>
                <span className="block text-xs text-rally">● Synced via InsForge</span>
              </div>
              <button
                onClick={async () => {
                  await insforge.auth.signOut();
                  setAuthUser(null);
                }}
                className="rounded-full border border-ink/15 px-3.5 py-1.5 text-xs font-semibold text-ink-soft hover:border-ink/40 hover:text-ink transition-colors"
              >
                Sign Out
              </button>
            </div>
          ) : (
            <div className="flex items-center justify-between">
              <div>
                <span className="block text-sm font-semibold text-ink">Guest Mode</span>
                <span className="block text-xs text-ink-soft">Sign in to save your debate journey</span>
              </div>
              <button
                onClick={() => setShowAuthModal(true)}
                className="rounded-full bg-rally px-4 py-2 text-xs font-semibold text-white hover:bg-rally-deep transition-colors"
              >
                Sign In / Up
              </button>
            </div>
          )}
        </div>
      </section>

      <section className="mt-10 border-t border-ink/10 pt-6">
        <button
          onClick={() => {
            reset();
            router.replace("/onboarding");
          }}
          className="text-sm font-medium text-coral underline underline-offset-4"
        >
          Reset demo state & redo onboarding
        </button>
      </section>

      {saved && (
        <p role="status" className="fixed bottom-24 left-1/2 -translate-x-1/2 rounded-full bg-ink px-4 py-2 text-sm text-white">
          Saved
        </p>
      )}

      <AuthModal
        isOpen={showAuthModal}
        onClose={() => setShowAuthModal(false)}
        onSuccess={(u) => setAuthUser(u)}
      />

      <TabBar />
    </main>
  );
}
