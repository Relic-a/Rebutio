export function StarRow({ stars, size = "md" }: { stars: number; size?: "sm" | "md" | "lg" }) {
  const dim = { sm: 15, md: 22, lg: 32 }[size];
  return (
    <span className="inline-flex items-center gap-[3px]" role="img" aria-label={`${stars} of 3 stars`}>
      {[0, 1, 2].map((i) => {
        const filled = i < stars;
        return (
          <svg
            key={i}
            width={dim}
            height={dim}
            viewBox="0 0 24 24"
            aria-hidden
            className={filled ? "drop-shadow-[0_2px_6px_rgba(232,155,46,0.55)]" : "opacity-70"}
          >
            <defs>
              <linearGradient id={`star-g-${size}-${i}`} x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#f5c15d" />
                <stop offset="100%" stopColor="#e89b2e" />
              </linearGradient>
            </defs>
            <path
              d="M12 2.6l2.83 5.83 6.42.83-4.7 4.5 1.18 6.36L12 17.05l-5.73 3.07 1.18-6.36-4.7-4.5 6.42-.83L12 2.6z"
              fill={filled ? `url(#star-g-${size}-${i})` : "rgba(28,33,29,0.12)"}
              stroke={filled ? "#9a5f0f" : "rgba(28,33,29,0.14)"}
              strokeWidth="1.1"
              strokeLinejoin="round"
            />
          </svg>
        );
      })}
    </span>
  );
}
