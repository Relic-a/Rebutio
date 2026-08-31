# Rebutio Observability & Diagnostics Architecture

This document describes the structured logging, diagnostics, correlation, and prompt-leak protection layer implemented across the Rebutio backend and frontend.

---

## 1. Overview & Architecture

Rebutio uses a unified structured logging and observability pipeline designed for production safety, debuggability, and strict user privacy:

1. **Backend Core Engine (`backend/app/observability/`)**:
   - Built on `structlog` for high-throughput, contextual logging.
   - Dual-mode output: human-friendly colored output (`LOG_FORMAT=console`) for local development, and line-delimited JSON (`LOG_FORMAT=json`) for production log aggregation systems (Datadog, CloudWatch, Loki, GCP Cloud Logging).
   - Async-safe context variables (`backend/app/observability/context.py`) automatically attach correlation IDs (`request_id`, `user_id`, `session_id`, `turn_id`, `debate_id`, `background_task_id`, `provider_request_id`) across concurrent coroutines and background tasks.

2. **Middleware & ASGI Layer (`backend/app/observability/middleware.py`)**:
   - Generates or preserves unique `request_id` (`req_<uuid>`) on every incoming request.
   - Attaches `X-Request-ID` to all HTTP responses.
   - Emits `http.request.started`, `http.request.completed`, and `http.request.failed` events with execution duration in milliseconds and client IP/route info.

3. **Privacy & Redaction Processor (`backend/app/observability/redaction.py`)**:
   - Automatically redacts sensitive fields (`authorization`, `api_key`, `secret`, `password`, `cookie`, `encryption_key`, `token`, etc.).
   - Explicitly preserves token usage metrics (`input_tokens`, `output_tokens`, `total_tokens`, `max_tokens`, `tokens_per_second`).
   - Normal production logs **never dump raw audio bytes, denoised audio, user transcripts, phoneme sequences, or full LLM completion bodies**.

4. **AI Gateway Diagnostics & Guardrails (`backend/app/observability/diagnostics.py`)**:
   - Emits safe structural message metadata (`message_roles`, `message_structures` with character counts and sha256 hashes) instead of raw prompt text.
   - Explicit prompt versioning (`debate_opponent:v1`, `topic_generator:v1`, etc.).
   - Defensive prompt-leak heuristic check (`detect_prompt_leak`) inspects generated text before delivery. If prompt/instruction leakage is detected, it logs `ai.prompt_leak_suspected` and automatically triggers a controlled fallback so leaked text never reaches TTS or the frontend.

5. **Modal Client & Remote Worker (`backend/app/services/modal/client.py`, `backend/modal/speech_analysis.py`)**:
   - Logs remote worker initialization, model loading, memory snapshots, and inference timing.
   - Forwards request/session/turn correlation IDs.

6. **Frontend Logger Abstraction (`frontend/lib/logger.ts`)**:
   - Provides `logger.debug()`, `logger.info()`, `logger.warn()`, `logger.error()`.
   - Automatically tracks backend `request_id` from HTTP response headers and includes it on failed requests and state transitions.

---

## 2. Configuration & Environment Variables

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `LOG_LEVEL` | `str` | `INFO` | Minimum log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). |
| `LOG_FORMAT` | `str` | `console` | `console` (human-readable, colorized) or `json` (machine-readable structured JSON). |
| `LOG_AI_CONTENT` | `bool` | `false` | **Development-only** debug flag. When `true`, logs bounded, truncated snippets of AI input/output labeled `[SENSITIVE_DEBUG]`. **NEVER enable in production or commit to `.env`.** |
| `DB_SLOW_QUERY_MS` | `int` | `500` | Slow query threshold in milliseconds. Queries exceeding this duration emit `db.operation.slow`. |

---

## 3. Querying & Inspecting Logs

### Find all logs for a specific request
```bash
# JSON logs
grep '"request_id": "req_a1b2c3d4"' app.log | jq .

# Or using ripgrep
rg 'req_a1b2c3d4' app.log
```

### Trace a complete debate session lifecycle
```bash
rg 'session-8f3a21b9' app.log
```
This surfaces:
1. `debate.session.started` (session creation)
2. `debate.turn.received` (turn 1 user submission)
3. `speech.transcription.started` / `speech.transcription.completed` (MAI STT)
4. `speech.phoneme_processing.dispatched` (Modal CTC phoneme analysis)
5. `debate.opponent_generation.started` / `debate.opponent_generation.completed` (DeepSeek V4 Pro)
6. `debate.tts.started` / `debate.tts.completed` (Gemini Flash TTS)
7. `session.state_changed` (`user_turn_submitted` -> `opponent_thinking` -> `opponent_ready`)
8. `background_task.started` / `background_task.completed` (evidence saving, topic inventory refill)
9. `debate_review.started` / `debate_review.completed` / `session.completed`

### Inspect AI Provider Performance & Token Usage
```bash
rg '"event": "ai.request.completed"' app.log | jq '{role: .role, model: .model, duration_ms: .duration_ms, input_tokens: .input_tokens, output_tokens: .output_tokens, provider_req_id: .provider_request_id}'
```

### Check for Provider Fallbacks or Retries
```bash
rg '"event": "(ai.provider_fallback|provider.retry)"' app.log | jq .
```

---

## 4. Root Cause Analysis & Fix: Onboarding Prompt-Leak Bug

### Symptom
During the onboarding debate opening turn, Rebutio returned instruction text:
```text
Rebutio responds

Rebutio must speak first and open the debate. Rebutio must NOT wait for the user to speak first.

Rebutio should deliver an opening argument supporting DISAGREE...
```

### Root Cause Diagnosis
1. **Root Cause Category**: **Category 2 & 5** (Prompt framing and lack of explicit user-turn anchor on opening round causing model to output third-person meta-directive instructions).
2. **Mechanism**:
   - In opening turns or when conversational message history lacked an anchored user-side turn, the model prompt structure ended without a clear interlocutor turn.
   - Without strict negative system constraints prohibiting third-person meta-commentary, reasoning models (such as DeepSeek / OpenRouter models) outputted stage directions and planning notes (`"Rebutio must speak first..."`, `"Rebutio responds..."`) instead of in-character spoken dialogue.

### Resolution
1. **Prompt Anchoring & Anti-Leak Constraints (`backend/app/prompts/debate_opponent.py`)**:
   - Added explicit user-turn anchoring in `build_opponent_prompt`: if `turn_history` is empty, it automatically injects a properly formatted user opening message.
   - Added strict negative constraints to `OPPONENT_SYSTEM_PROMPT`:
     `NEVER output third-person meta-commentary, stage directions, or descriptions of what Rebutio must do (e.g. NEVER output 'Rebutio responds', 'Rebutio must speak first', 'Rebutio should deliver...', 'Opening argument:').`
     `Always speak directly in first-person dialogue ('I', 'we') addressing the user ('you').`
2. **Defensive Response Sanitizer & Guardrail (`backend/app/services/ai/gateway.py` & `backend/app/observability/diagnostics.py`)**:
   - Added `_clean_opponent_text` to strip any lingering speaker prefix headers.
   - Integrated `detect_prompt_leak`: if any high-confidence prompt leak pattern is detected, it logs `ai.prompt_leak_suspected` and transparently routes to a curated, high-quality debate fallback argument so leaked text is never delivered to TTS or the user.
3. **Regression Tests (`backend/tests/test_onboarding_regression.py`)**:
   - Verified opening turn delivers a clean 2–4 sentence counterargument.
   - Verified that simulated rogue LLM instruction leaks trigger guardrail fallback and logging.
