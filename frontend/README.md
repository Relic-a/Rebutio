# Rebutio — frontend V1

Spoken-debate English learning app. Next.js (App Router) + TypeScript + Tailwind v4 + Framer Motion + Zustand.

## Run

```bash
npm install
npm run dev
```

The app is fully demoable without a backend: `lib/api/index.ts` exposes an `AppService`
boundary with a mock implementation (`createMockService`), and all product content lives in
`lib/mock/fixtures.ts` (demo fixtures only — replace with backend-provided content).

## Architecture

- `lib/types.ts` — loose, defensive contracts (DebateSession, DebateReview, …)
- `lib/api/` — application service boundary; components never touch providers or transports
- `lib/media/capture.ts` — microphone capture adapter (semantic events only, with graceful text fallback)
- `lib/state/store.ts` — persisted demo state (onboarding, XP, streak, stars, record)
- `app/onboarding` — 9-step onboarding; the first spar doubles as informal placement
- `app/debate` — briefing + live turn-based debate (rally-dot pacing, thinking states)
- `app/results` — completion → outcome (never blocks progression) → coaching → full language feedback
- `app/home`, `app/path`, `app/progress`, `app/profile`

## Demo walkthrough

Open the app → onboarding → pick goals/comfort/interests/intensity → 3-turn first spar →
mic permission (contextual) → debate → thinking animation → opponent responses →
review → results (stars, XP, streak, disagree-with-result) → home → path → progress.

Debate outcome and learning progression are independent: the mock reviews include a
session where the user **loses the debate but earns 3 stars**.
