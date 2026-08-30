"use client";

/** Rebutio logo mark: two opposing speech bubbles sparring. */
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-2" aria-hidden>
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none">
        <rect x="3" y="6" width="20" height="14" rx="7" fill="#127A63" />
        <path d="M10 20l-2 6 7-4" fill="#127A63" />
        <rect x="17" y="19" width="20" height="14" rx="7" fill="#E4593F" />
        <path d="M30 33l2 6-7-4" fill="#E4593F" />
        <circle cx="11" cy="13" r="2.2" fill="#FAF6EF" />
        <circle cx="17" cy="13" r="2.2" fill="#FAF6EF" />
        <circle cx="29" cy="26" r="2.2" fill="#FAF6EF" />
      </svg>
      <span className="font-display text-xl font-bold tracking-tight">Rebutio</span>
    </span>
  );
}
