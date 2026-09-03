"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const tabs = [
  { href: "/home", label: "Home", icon: "M4 11l8-7 8 7v9a1 1 0 01-1 1h-5v-6H10v6H5a1 1 0 01-1-1z" },
  { href: "/path", label: "Path", icon: "M6 3h12v6H6zm0 12h12v6H6zM12 9v4m0 0h0" },
  { href: "/coach", label: "Coach", icon: "M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z" },
  { href: "/progress", label: "Progress", icon: "M4 20V10m6 10V4m6 16v-7m4 7H2" },
  { href: "/profile", label: "Profile", icon: "M12 12a4 4 0 100-8 4 4 0 000 8zm-8 8a8 8 0 0116 0" },
];

export function TabBar() {
  const pathname = usePathname();
  return (
    <nav aria-label="Main navigation" className="fixed inset-x-0 bottom-0 z-40 px-4 pb-[calc(0.9rem+env(safe-area-inset-bottom))] pt-2">
      <div className="mx-auto flex w-full max-w-md items-stretch justify-between gap-1 rounded-[1.75rem] border border-white/40 bg-ink/[0.82] p-1.5 shadow-[0_20px_48px_-16px_rgba(28,33,29,0.55),inset_0_1px_0_rgba(255,255,255,0.18)] backdrop-blur-2xl">
        {tabs.map((t) => {
          const active = pathname === t.href || (t.href !== "/home" && pathname.startsWith(t.href));
          return (
            <Link
              key={t.href}
              href={t.href}
              aria-current={active ? "page" : undefined}
              className={`group relative flex min-w-0 flex-1 flex-col items-center gap-1 rounded-2xl px-2 py-2.5 text-[11px] font-semibold transition-all duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] ${
                active ? "bg-[#faf6ef] text-ink shadow-[inset_0_1px_0_rgba(255,255,255,0.9),0_8px_20px_-8px_rgba(0,0,0,0.5)]" : "text-white/60 hover:bg-white/10 hover:text-white"
              }`}
            >
              {active && <span className="absolute -top-1 h-1 w-8 rounded-full bg-amber shadow-[0_0_12px_rgba(232,155,46,0.9)]" aria-hidden />}
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={active ? 2.1 : 1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden className="transition-transform duration-300 group-active:scale-90">
                <path d={t.icon} />
              </svg>
              {t.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
