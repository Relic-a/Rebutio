"use client";

/** Rebutio logo mark: two opposing speech bubbles sparring. */
export function Logo({ size = 32, withWordmark = true }: { size?: number; withWordmark?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5" aria-hidden>
      <span
        className="relative inline-flex items-center justify-center rounded-2xl border border-white/25 bg-gradient-to-br from-rally-deep via-rally to-rally-deep p-[3px] shadow-[0_10px_24px_-8px_rgba(14,122,95,0.7),inset_0_1px_0_rgba(255,255,255,0.35)]"
        style={{ width: size + 10, height: size + 10 }}
      >
        <svg width={size} height={size} viewBox="0 0 40 40" fill="none" className="drop-shadow-sm">
          <rect x="3" y="6" width="20" height="14" rx="7" fill="#FAF6EF" />
          <path d="M10 20l-2 6 7-4" fill="#FAF6EF" />
          <rect x="17" y="19" width="20" height="14" rx="7" fill="#E89B2E" />
          <path d="M30 33l2 6-7-4" fill="#E89B2E" />
          <circle cx="11" cy="13" r="2.2" fill="#0A4A3A" />
          <circle cx="17" cy="13" r="2.2" fill="#0A4A3A" />
          <circle cx="29" cy="26" r="2.2" fill="#083A2E" />
        </svg>
      </span>
      {withWordmark && <span className="font-display text-xl font-black tracking-tight">Rebutio</span>}
    </span>
  );
}
