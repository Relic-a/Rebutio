# Rebutio Workbench

An isolated, modular workbench for testing, prompt iteration, and state inspection in Rebutio.

## Why This Exists

In end-to-end runs, testing the application requires walking through the entire pipeline: generating a topic, running 3-4 debate turns with STT/TTS and Modal phonemes, waiting for review finalization, and navigating to coaching. When tuning prompts or scoring rubrics, this tight coupling kills iteration speed.

The **Rebutio Workbench** divides the program into 4 distinct logical parts, exposes their inputs, prompts, and outputs, and provides state continuity so downstream components (such as the Reviewer and Coach) can continue from saved states or pre-seeded golden presets in milliseconds.

---

## The 4 Logical Modules

| Part | Role | State Input | Exposed Outputs |
|---|---|---|---|
| **1. Topic Generator** | Creates motion propositions matching skills, difficulty & interests | `TopicGeneratorInput` | Generated topics, prompt messages, raw LLM completion, latency |
| **2. Debate Mode** | Simulates turn-by-turn arguments & opponent rebuttals | `DebateState` (turns 1..N) | Opponent rebuttal text, closing detection, turn history, prompt messages |
| **3. Reviewer (The Scorer)** | Adjudicates debate, awards 0-3 stars, technique/grammar/vocab/delivery rubrics, language findings | `DebateState` (completed) | Score cards + rubrics side-by-side, win/loss outcome, stars note, phoneme findings, prompts |
| **4. Coach Mode** | Opening coaching analysis, interactive drills/chat with tool loops, long-term memory updates | `CoachState` (Review + Debate + Memory) | Opening analysis card, drill suggestions, pronunciation chips, tool executions, memory markdown diff |

---

## State Continuity & Presets

Each module can serialize its state to a clean JSON file and load an earlier state to continue from:

```
Topic Generator (TopicState)
       │
       ▼
Debate Mode (DebateState) ──[Turn-by-turn with Opponent]──► Completed DebateState
                                                                   │
                                                                   ▼
                                                            Reviewer Mode (Scorer)
                                                                   │
                                                                   ▼
                                                             ReviewState
                                                                   │
                                                                   ▼
                                                              Coach Mode
                                              ┌────────────────────┴────────────────────┐
                                              ▼                                         ▼
                                     Coach Memory Update                       Opening Analysis & Chat
```

Pre-seeded golden presets in `workbench/state/presets/`:
- `topics/standard_refutation.json`: Target skill inputs & compact speech findings.
- `debates/turn1_in_progress.json`: State at turn 1, ready for opponent rebuttal.
- `debates/turn2_in_progress.json`: State at turn 2, ready for opponent rebuttal.
- `debates/completed_strong.json`: 3-turn high quality debate with speech metrics, ready for Reviewer.
- `debates/completed_insufficient.json`: Short 1-turn debate testing edge case of insufficient evidence.
- `reviews/strong_review.json`: Scored review with 3 stars and rubrics, ready for Coach.
- `coach/ready_for_opening.json`: Coach state ready for opening analysis and chat drills.

---

## CLI Usage

Run commands with Python in `backend/.venv`:

```bash
# List available presets and saved states
python -m workbench.cli state list

# 1. Topic Generator: Generate topics and inspect prompt
python -m workbench.cli topic generate --skill direct_refutation --difficulty steady --count 3 --show-prompt

# 2. Debate Mode: Step one turn and generate opponent response
python -m workbench.cli debate step --state debates/turn1_in_progress.json --text "Your counterargument here"

# 2b. Debate Mode: Simulate an entire debate
python -m workbench.cli debate sim --topic "AI will reduce junior developer jobs." --side agree

# 3. Reviewer: Score a completed debate immediately (<1ms mock or live AI)
python -m workbench.cli review run --state debates/completed_strong.json --show-prompts

# Test edge cases: Insufficient evidence handling
python -m workbench.cli review run --state debates/completed_insufficient.json

# 4. Coach Mode: Generate opening analysis
python -m workbench.cli coach opening --state coach/ready_for_opening.json

# 4b. Coach Mode: Chat with the coach
python -m workbench.cli coach chat --state coach/ready_for_opening.json --message "Give me a 1-minute practice drill"

# 4c. Coach Mode: Update long-term memory and inspect diff
python -m workbench.cli coach memory --state coach/ready_for_opening.json

# 5. Full Pipeline: Run all 4 modules sequentially
python -m workbench.cli pipeline --skill direct_refutation

# 6. Web Workbench: Start the interactive browser testbed
python -m workbench.cli serve --port 8008
```

Add `--live` to any command to call the actual AI Gateway using Router.com / OpenRouter credentials in `.env`.

---

## Web Workbench

Launch the visual testbed with:

```bash
python -m workbench.cli serve --port 8008
```

Then open `http://localhost:8008` in your browser. The web workbench allows you to:
- Test each module in isolation via 4 tabs.
- Load presets with one click.
- Step through debate turns interactively.
- Send state from Debate Mode directly to Reviewer, and from Reviewer directly to Coach.
- Toggle between Instant Mock Mode (1ms) and Live AI Gateway.
- Export states as JSON to disk.
