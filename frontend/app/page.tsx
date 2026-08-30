"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useStore } from "@/lib/state/store";
import { Logo } from "@/components/shared/Logo";

export default function Gate() {
  const router = useRouter();
  const onboarded = useStore((s) => s.onboarded);
  const hydrated = useStore.persist?.hasHydrated?.() ?? false;

  useEffect(() => {
    if (hydrated) router.replace(onboarded ? "/home" : "/onboarding");
  }, [hydrated, onboarded, router]);

  return (
    <main className="flex min-h-dvh items-center justify-center">
      <Logo size={44} />
    </main>
  );
}
