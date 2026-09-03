"use client";

import { Suspense } from "react";
import DebatePage from "../page";

export default function DebateByIdPage() {
  return (
    <Suspense>
      <DebatePage />
    </Suspense>
  );
}
