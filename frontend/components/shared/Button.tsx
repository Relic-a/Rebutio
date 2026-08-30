"use client";

import { motion } from "framer-motion";

export function Button({
  children,
  onClick,
  variant = "primary",
  disabled,
  className = "",
  type = "button",
  "aria-label": ariaLabel,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "coral";
  disabled?: boolean;
  className?: string;
  type?: "button" | "submit";
  "aria-label"?: string;
}) {
  const styles = {
    primary: "bg-rally text-white hover:bg-rally-deep disabled:bg-ink-soft/40",
    secondary: "bg-white text-ink border-2 border-ink/15 hover:border-ink/40",
    ghost: "bg-transparent text-ink-soft hover:text-ink",
    coral: "bg-coral text-white hover:bg-coral/90",
  }[variant];
  return (
    <motion.button
      type={type}
      aria-label={ariaLabel}
      whileTap={disabled ? undefined : { scale: 0.97 }}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-full px-6 py-4 text-base font-semibold transition-colors disabled:cursor-not-allowed ${styles} ${className}`}
    >
      {children}
    </motion.button>
  );
}
