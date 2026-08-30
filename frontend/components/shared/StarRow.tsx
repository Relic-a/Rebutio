"use client";

export function StarRow({ stars, size = "md" }: { stars: number; size?: "sm" | "md" | "lg" }) {
  const s = { sm: "text-base", md: "text-2xl", lg: "text-4xl" }[size];
  return (
    <span className={`${s} tracking-wide`} role="img" aria-label={`${stars} of 3 stars`}>
      {[0, 1, 2].map((i) => (
        <span key={i} className={i < stars ? "text-amber" : "text-ink/15"}>
          ★
        </span>
      ))}
    </span>
  );
}
