"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/shared/Button";
import { insforge } from "@/lib/api";
import { logger } from "@/lib/logger";

type AuthMode = "signin" | "signup";

export function AuthModal({
  isOpen,
  onClose,
  onSuccess,
}: {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (user: any) => void;
}) {
  const [mode, setMode] = useState<AuthMode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    setLoading(true);

    try {
      if (mode === "signup") {
        const { data, error: signUpErr } = await insforge.auth.signUp({
          email: email.trim(),
          password,
          name: name.trim() || undefined,
        });

        if (signUpErr) {
          setError(signUpErr.message || "Failed to create account");
          return;
        }

        if (data?.accessToken) {
          setMessage("Account created and signed in!");
          setTimeout(() => {
            onSuccess?.(data.user);
            onClose();
          }, 600);
        } else {
          setMessage("Account created! Please check your email if verification is required.");
        }
      } else {
        const { data, error: signInErr } = await insforge.auth.signInWithPassword({
          email: email.trim(),
          password,
        });

        if (signInErr) {
          setError(signInErr.message || "Invalid email or password");
          return;
        }

        if (data?.accessToken) {
          setMessage("Signed in successfully!");
          setTimeout(() => {
            onSuccess?.(data.user);
            onClose();
          }, 600);
        }
      }
    } catch (err: any) {
      logger.error("auth.action_failed", { mode }, err);
      setError(err?.message || "An unexpected error occurred during authentication.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 bg-ink/60 backdrop-blur-sm"
        />

        {/* Modal Card */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 16 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 16 }}
          className="relative z-10 w-full max-w-sm overflow-hidden rounded-3xl bg-white p-6 shadow-2xl"
        >
          <div className="flex items-center justify-between">
            <h2 className="font-display text-2xl font-bold tracking-tight">
              {mode === "signin" ? "Sign In" : "Create Account"}
            </h2>
            <button
              onClick={onClose}
              className="rounded-full p-2 text-ink-soft hover:bg-ink/5 hover:text-ink transition-colors"
              aria-label="Close"
            >
              ✕
            </button>
          </div>

          <p className="mt-1 text-xs text-ink-soft">
            {mode === "signin"
              ? "Sign in to sync your debate progression and audio history."
              : "Create an InsForge account to save your debate journey."}
          </p>

          <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
            {mode === "signup" && (
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-ink-soft">
                  Name (Optional)
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Alex"
                  className="mt-1 w-full rounded-2xl border-2 border-ink/10 px-4 py-3 text-sm focus:border-rally focus:outline-none"
                />
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-ink-soft">
                Email
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="mt-1 w-full rounded-2xl border-2 border-ink/10 px-4 py-3 text-sm focus:border-rally focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-ink-soft">
                Password
              </label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="mt-1 w-full rounded-2xl border-2 border-ink/10 px-4 py-3 text-sm focus:border-rally focus:outline-none"
              />
            </div>

            {error && (
              <p role="alert" className="rounded-xl bg-coral-soft p-3 text-xs font-medium text-coral">
                {error}
              </p>
            )}

            {message && (
              <p role="status" className="rounded-xl bg-rally-mist p-3 text-xs font-medium text-rally-deep">
                {message}
              </p>
            )}

            <Button type="submit" disabled={loading} className="mt-2 w-full">
              {loading ? "Please wait…" : mode === "signin" ? "Sign In" : "Create Account"}
            </Button>
          </form>

          <div className="mt-6 border-t border-ink/10 pt-4 text-center">
            {mode === "signin" ? (
              <p className="text-xs text-ink-soft">
                Don&apos;t have an account?{" "}
                <button
                  onClick={() => {
                    setError(null);
                    setMessage(null);
                    setMode("signup");
                  }}
                  className="font-semibold text-rally underline underline-offset-2"
                >
                  Sign up
                </button>
              </p>
            ) : (
              <p className="text-xs text-ink-soft">
                Already have an account?{" "}
                <button
                  onClick={() => {
                    setError(null);
                    setMessage(null);
                    setMode("signin");
                  }}
                  className="font-semibold text-rally underline underline-offset-2"
                >
                  Sign in
                </button>
              </p>
            )}
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
