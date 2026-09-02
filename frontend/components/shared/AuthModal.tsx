"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/shared/Button";
import { insforge } from "@/lib/api";
import { logger } from "@/lib/logger";

type AuthMode = "signin" | "signup" | "verify";

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
  const [verificationCode, setVerificationCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }

    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    setLoading(true);

    try {
      if (mode === "verify") {
        const { data, error: verifyErr } = await insforge.auth.verifyEmail({
          email: email.trim(),
          otp: verificationCode,
        });

        if (verifyErr) {
          setError(verifyErr.message || "That code is invalid or has expired.");
          return;
        }

        if (data?.accessToken) {
          setMessage("Email verified. You’re signed in!");
          setTimeout(() => {
            onSuccess?.(data.user);
            onClose();
          }, 600);
        }
      } else if (mode === "signup") {
        const { data, error: signUpErr } = await insforge.auth.signUp({
          email: email.trim(),
          password,
          name: name.trim() || undefined,
        });

        if (signUpErr) {
          setError(signUpErr.message || "Failed to create account");
          return;
        }

        if (data?.requireEmailVerification) {
          const { data: authConfig } = await insforge.auth.getPublicAuthConfig();

          if (authConfig?.verifyEmailMethod === "link") {
            setMessage("Account created. Check your email and open the verification link to continue.");
          } else {
            setVerificationCode("");
            setMode("verify");
            setMessage(`We sent a 6-digit verification code to ${email.trim()}.`);
          }
        } else if (data?.accessToken) {
          setMessage("Account created and signed in!");
          setTimeout(() => {
            onSuccess?.(data.user);
            onClose();
          }, 600);
        } else {
          setError("Your account was created, but Rebutio could not start a session. Please sign in.");
        }
      } else {
        const { data, error: signInErr } = await insforge.auth.signInWithPassword({
          email: email.trim(),
          password,
        });

        if (signInErr) {
          if ((signInErr as any).statusCode === 403) {
            setVerificationCode("");
            setMode("verify");
            setMessage(`Enter the verification code sent to ${email.trim()}.`);
            return;
          }
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

  async function handleResend() {
    setError(null);
    setMessage(null);
    setResending(true);

    try {
      const { error: resendErr } = await insforge.auth.resendVerificationEmail({
        email: email.trim(),
      });

      if (resendErr) {
        setError(resendErr.message || "We couldn’t resend the code. Please try again shortly.");
        return;
      }

      setMessage(`A new verification code was sent to ${email.trim()}.`);
    } catch (err: any) {
      logger.error("auth.verification_resend_failed", {}, err);
      setError(err?.message || "We couldn’t resend the code. Please try again shortly.");
    } finally {
      setResending(false);
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
          role="dialog"
          aria-modal="true"
          aria-labelledby="auth-dialog-title"
          initial={{ opacity: 0, scale: 0.95, y: 16 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 16 }}
          className="relative z-10 w-full max-w-sm overflow-hidden rounded-3xl bg-white p-6 shadow-2xl"
        >
          <div className="flex items-center justify-between">
            <h2 id="auth-dialog-title" className="font-display text-2xl font-bold tracking-tight">
              {mode === "signin" ? "Sign In" : mode === "signup" ? "Create Account" : "Verify Your Email"}
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
              : mode === "signup"
                ? "Create a Rebutio account to save your debate journey."
                : `Enter the 6-digit code sent to ${email.trim()}.`}
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

            {mode === "verify" ? (
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-ink-soft" htmlFor="verification-code">
                  Verification code
                </label>
                <input
                  id="verification-code"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  autoFocus
                  required
                  minLength={6}
                  maxLength={6}
                  pattern="[0-9]{6}"
                  value={verificationCode}
                  onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="123456"
                  className="mt-1 w-full rounded-2xl border-2 border-ink/10 px-4 py-3 text-center font-mono text-xl tracking-[0.35em] focus:border-rally focus:outline-none"
                />
              </div>
            ) : (
              <>
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-ink-soft">
                    Email
                  </label>
                  <input
                    type="email"
                    autoFocus={mode === "signin"}
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
              </>
            )}

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

            <Button
              type="submit"
              disabled={loading || (mode === "verify" && verificationCode.length !== 6)}
              className="mt-2 w-full"
            >
              {loading ? "Please wait…" : mode === "signin" ? "Sign In" : mode === "signup" ? "Create Account" : "Verify Email"}
            </Button>
          </form>

          <div className="mt-6 border-t border-ink/10 pt-4 text-center">
            {mode === "verify" ? (
              <div className="flex items-center justify-center gap-3 text-xs text-ink-soft">
                <button
                  type="button"
                  disabled={resending}
                  onClick={() => void handleResend()}
                  className="font-semibold text-rally underline underline-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {resending ? "Sending…" : "Resend code"}
                </button>
                <span aria-hidden="true">·</span>
                <button
                  type="button"
                  onClick={() => {
                    setError(null);
                    setMessage(null);
                    setVerificationCode("");
                    setMode("signin");
                  }}
                  className="font-semibold text-rally underline underline-offset-2"
                >
                  Back to sign in
                </button>
              </div>
            ) : mode === "signin" ? (
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
