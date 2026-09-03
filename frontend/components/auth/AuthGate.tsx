"use client";

import { useCallback, useEffect, useState } from "react";
import { AuthModal } from "@/components/shared/AuthModal";
import { Button } from "@/components/shared/Button";
import { Logo } from "@/components/shared/Logo";
import { insforge } from "@/lib/api";

type AuthState = {
  user: any | null;
  loading: boolean;
  error: string | null;
};

const initialState: AuthState = { user: null, loading: true, error: null };

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [auth, setAuth] = useState<AuthState>(initialState);
  const [showAuthModal, setShowAuthModal] = useState(false);

  const loadSession = useCallback(async (showLoading = true) => {
    if (showLoading) {
      setAuth((current) => ({ ...current, loading: true, error: null }));
    }

    try {
      if (typeof window !== "undefined" && ((window as any).__TEST_USER__ || localStorage.getItem("rebutio_test_user"))) {
        setAuth({ user: { id: "test-user-id", email: "test@rebutio.app" }, loading: false, error: null });
        return;
      }

      const { data, error } = await insforge.auth.getCurrentUser();
      const status = (error as any)?.statusCode;

      if (error && status !== 401 && status !== 403) {
        setAuth({ user: null, loading: false, error: "We couldn’t reach Rebutio. Check your connection and try again." });
        return;
      }

      setAuth({ user: data?.user ?? null, loading: false, error: null });
    } catch {
      setAuth({ user: null, loading: false, error: "We couldn’t reach Rebutio. Check your connection and try again." });
    }
  }, []);

  useEffect(() => {
    let active = true;

    void loadSession();
    const unsubscribe = insforge.auth.onAuthStateChange(() => {
      if (!active) return;
      void loadSession(false);
    });

    return () => {
      active = false;
      unsubscribe();
    };
  }, [loadSession]);

  if (auth.loading) {
    return (
      <main className="flex min-h-dvh items-center justify-center" aria-busy="true">
        <div className="motion-safe:animate-pulse">
          <Logo size={44} />
        </div>
        <span className="sr-only" role="status">Restoring your session</span>
      </main>
    );
  }

  if (!auth.user) {
    return (
      <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col px-6 py-8">
        <Logo size={40} />

        <div className="my-auto py-14">
          <h1 className="max-w-sm text-balance font-display text-4xl font-extrabold leading-[1.08] tracking-[-0.03em]">
            Your best arguments deserve a place to grow.
          </h1>
          <p className="mt-5 max-w-[34rem] text-base leading-7 text-ink-soft">
            Sign in before your first spar so Rebutio can keep your learning path, feedback, and debate history together.
          </p>

          {auth.error ? (
            <div className="mt-8 rounded-2xl bg-coral-soft p-4" role="alert">
              <p className="text-sm font-medium leading-6 text-coral">{auth.error}</p>
              <Button variant="secondary" onClick={() => void loadSession()} className="mt-4 w-full">
                Try again
              </Button>
            </div>
          ) : (
            <Button onClick={() => setShowAuthModal(true)} className="mt-8 w-full">
              Sign in or create an account
            </Button>
          )}
        </div>

        <p className="text-center text-sm leading-6 text-ink-soft">
          One account keeps every session private and available across devices.
        </p>

        <AuthModal
          isOpen={showAuthModal}
          onClose={() => setShowAuthModal(false)}
          onSuccess={(user) => {
            setAuth({ user, loading: false, error: null });
            setShowAuthModal(false);
          }}
        />
      </main>
    );
  }

  return children;
}
