from typing import Any, Dict, List, Optional
from pydantic import BaseModel


# Centralized evidence thresholds
MIN_SUBSTANTIVE_USER_TURNS = 2
MIN_SUBSTANTIVE_USER_WORDS = 20
MIN_SINGLE_TURN_WORDS = 25
MIN_TURN_WORD_THRESHOLD = 5


class DebateEvidenceAssessment(BaseModel):
    has_sufficient_evidence: bool
    has_sufficient_delivery_evidence: bool
    user_turns_count: int
    substantive_turns_count: int
    total_user_words: int
    has_audio_evidence: bool
    insufficient_reason: Optional[str] = None


def assess_debate_evidence(
    turns: List[Any],
    temporary_evidence: Optional[List[Dict[str, Any]]] = None,
) -> DebateEvidenceAssessment:
    """
    Deterministically assesses whether a debate session contains sufficient
    substantive user argumentation and acoustic evidence to perform full evaluation.
    """
    user_turns = []
    user_word_counts = []
    has_audio = False

    for t in turns:
        # Support dicts or ORM DebateTurn objects
        speaker = getattr(t, "speaker", None) or (t.get("speaker") if isinstance(t, dict) else None)
        if speaker != "user":
            continue

        raw_text = getattr(t, "text", None) or (t.get("text") if isinstance(t, dict) else None) or ""
        text = raw_text.strip()
        words = len(text.split()) if text else 0

        user_turns.append(text)
        user_word_counts.append(words)

        audio_avail = getattr(t, "audio_available", False) or (t.get("audio_available", False) if isinstance(t, dict) else False)
        dur_sec = getattr(t, "duration_sec", 0.0) or (t.get("duration_sec", 0.0) if isinstance(t, dict) else 0.0)
        if audio_avail or dur_sec > 1.0:
            has_audio = True

    # Check acoustic evidence from temporary evidence records if available
    if temporary_evidence and not has_audio:
        for ev in temporary_evidence:
            if ev.get("phonemes") or ev.get("speech_metrics") or (ev.get("duration_ms", 0) > 1000):
                has_audio = True
                break

    user_turns_count = len(user_turns)
    total_user_words = sum(user_word_counts)
    substantive_turns = [w for w in user_word_counts if w >= MIN_TURN_WORD_THRESHOLD]
    substantive_turns_count = len(substantive_turns)

    # Deterministic sufficiency check:
    # 1. Total user words must meet minimum threshold (>= 20 words)
    # 2. Must either have at least 2 substantive turns (>= 5 words each) OR 1 deep opening (>= 25 words)
    has_sufficient_evidence = False
    insufficient_reason = None

    if user_turns_count == 0 or total_user_words == 0:
        insufficient_reason = "no_user_speech"
    elif total_user_words < MIN_SUBSTANTIVE_USER_WORDS:
        insufficient_reason = f"insufficient_words_{total_user_words}_below_{MIN_SUBSTANTIVE_USER_WORDS}"
    elif substantive_turns_count < MIN_SUBSTANTIVE_USER_TURNS and total_user_words < MIN_SINGLE_TURN_WORDS:
        insufficient_reason = f"insufficient_turns_{substantive_turns_count}_below_{MIN_SUBSTANTIVE_USER_TURNS}"
    else:
        has_sufficient_evidence = True

    has_sufficient_delivery_evidence = has_sufficient_evidence and has_audio

    return DebateEvidenceAssessment(
        has_sufficient_evidence=has_sufficient_evidence,
        has_sufficient_delivery_evidence=has_sufficient_delivery_evidence,
        user_turns_count=user_turns_count,
        substantive_turns_count=substantive_turns_count,
        total_user_words=total_user_words,
        has_audio_evidence=has_audio,
        insufficient_reason=insufficient_reason,
    )
