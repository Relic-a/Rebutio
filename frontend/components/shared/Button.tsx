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
    primary:
      "bg-rally text-white hover:bg-rally-deep disabled:bg-ink-soft/40 shadow-[0_12px_28px_-10px_rgba(14,122,95,0.65),inset_0_1px_0_rgba(255,255,255,0.25)] hover:shadow-[0_16px_32px_-10px_rgba(14,122,95,0.7),inset_0_1px_0_rgba(255,255,255,0.25)] hover:-translate-y-[1px]",
    secondary:
      "bg-[#fffdf7] text-ink border border-ink/12 hover:border-ink/25 hover:-translate-y-[1px] shadow-[0_8px_20px_-12px_rgba(28,33,29,0.4),inset_0_1px_0_rgba(255,255,255,0.8)]",
    ghost: "bg-transparent text-ink-soft hover:text-ink hover:bg-ink/5",
    coral:
      "bg-coral text-white hover:bg-coral-deep shadow-[0_12px_28px_-10px_rgba(228,87,61,0.6),inset_0_1px_0_rgba(255,255,255,0.25)] hover:-translate-y-[1px]",
  }[variant];
  return (
    <motion.button
      type={type}
      aria-label={ariaLabel}
      whileTap={disabled ? undefined : { scale: 0.97, y: 1 }}
      transition={{ type: "spring", stiffness: 500, damping: 32 }}
      onClick={onClick}
      disabled={disabled}
      className={`btn-sheen group inline-flex cursor-pointer items-center justify-center gap-2 rounded-full px-6 py-4 text-base font-semibold transition-all duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] active:translate-y-[1px] disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none ${styles} ${className}`}
    >
      <span className="relative z-[2] inline-flex items-center gap-2">{children}</span>
    </motion.button>
  );
}
