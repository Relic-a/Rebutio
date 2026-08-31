import hashlib
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class MessageStructureMetadata(BaseModel):
    message_count: int
    system_message_count: int
    user_message_count: int
    assistant_message_count: int
    input_character_count: int
    message_roles: List[str]
    message_structures: List[Dict[str, Any]]
    structured_output: bool = False


class PromptLeakReport(BaseModel):
    is_leak_suspected: bool
    confidence: str  # "high", "low", "none"
    matched_patterns: List[str]
    response_hash: str
    response_char_count: int
    response_word_count: int


# Instruction phrases and prompt header signatures that indicate prompt/instruction leakage
INSTRUCTION_SIGNATURES = [
    # Explicit prompt section headings
    r"\byour identity\b",
    r"\byour debating style\b",
    r"\boutput constraints\b",
    r"\boutput format\b",
    r"\bdebate context\b",
    r"\btarget skill focus\b",
    r"\brebutio's assigned side\b",
    r"\buser's side\b",
    r"\bsystem prompt\b",
    r"\bdeveloper message\b",
    r"\btask:\b",
    r"\binstructions:\b",
    r"\bstrictly the user's debate opponent\b",
    r"\bnever praise the user's english\b",
    r"\bnever sound like an ai assistant\b",
    r"\bdo not use markdown\b",
    r"\bspeak approximately \d+ to \d+ sentences\b",
    r"\bwrite \d+ sentences\b",
    r"\brebutio responds\b",
    r"\brebutio must speak first\b",
    r"\brebutio must not wait\b",
    r"\brebutio should deliver an opening argument\b",
    r"\bsupporting (?:agree|disagree)\b",
    r"\byou must (?:speak|deliver|open|not wait|defend|argue|respond)\b",
    r"\bmust not (?:wait|praise|give|sound)\b",
]

COMPILED_INSTRUCTION_PATTERNS = [re.compile(p, re.IGNORECASE) for p in INSTRUCTION_SIGNATURES]


def compute_sha256(text: str) -> str:
    """Computes a hex SHA-256 hash of a string."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def extract_message_structure(messages: List[Dict[str, Any]], structured_output: bool = False) -> MessageStructureMetadata:
    """
    Extracts safe structural metadata from message lists without exposing actual user or prompt content.
    """
    sys_count = 0
    usr_count = 0
    asst_count = 0
    total_chars = 0
    roles = []
    structures = []

    for msg in messages:
        role = str(msg.get("role", "unknown"))
        content = str(msg.get("content", ""))
        chars = len(content)
        content_hash = compute_sha256(content)[:12]

        roles.append(role)
        total_chars += chars
        structures.append({
            "role": role,
            "chars": chars,
            "sha256": content_hash,
        })

        if role == "system":
            sys_count += 1
        elif role == "user":
            usr_count += 1
        elif role == "assistant":
            asst_count += 1

    return MessageStructureMetadata(
        message_count=len(messages),
        system_message_count=sys_count,
        user_message_count=usr_count,
        assistant_message_count=asst_count,
        input_character_count=total_chars,
        message_roles=roles,
        message_structures=structures,
        structured_output=structured_output,
    )


def detect_prompt_leak(text: str) -> PromptLeakReport:
    """
    Defensive heuristic detector for prompt/instruction leakage in model responses.
    Prefers false negatives over constant false positives.
    """
    if not text:
        return PromptLeakReport(
            is_leak_suspected=False,
            confidence="none",
            matched_patterns=[],
            response_hash=compute_sha256(""),
            response_char_count=0,
            response_word_count=0,
        )

    response_hash = compute_sha256(text)
    char_count = len(text)
    word_count = len(text.split())

    matched = []
    for pattern in COMPILED_INSTRUCTION_PATTERNS:
        match = pattern.search(text)
        if match:
            matched.append(match.group(0))

    # High-confidence indicators: explicit section headers or multiple instruction phrases
    is_high_confidence = False
    is_suspected = False
    confidence = "none"

    # Specific single strong markers that clearly indicate instructions
    strong_markers = [
        "your identity:",
        "your debating style:",
        "output constraints",
        "system prompt",
        "developer message",
        "task:",
        "instructions:",
        "strictly the user's debate opponent",
        "never praise the user's english",
        "rebutio must speak first",
        "rebutio must not wait",
        "rebutio responds",
        "rebutio should deliver an opening argument",
    ]
    low_text = text.lower()
    for marker in strong_markers:
        if marker in low_text:
            is_high_confidence = True
            break

    if is_high_confidence or len(matched) >= 2:
        is_suspected = True
        confidence = "high"
    elif len(matched) == 1:
        # Check if it's a generic phrase that might be a false positive
        matched_str = matched[0].lower()
        if "you must" in matched_str or "must not" in matched_str:
            # Single "you must" in normal debate speech might be conversational: "You must admit..."
            is_suspected = False
            confidence = "low"
        else:
            is_suspected = True
            confidence = "low"

    return PromptLeakReport(
        is_leak_suspected=is_suspected,
        confidence=confidence,
        matched_patterns=matched,
        response_hash=response_hash,
        response_char_count=char_count,
        response_word_count=word_count,
    )


def format_sensitive_debug(content: str, max_chars: int = 150) -> str:
    """
    Carefully bounded string formatting for local-only SENSITIVE_DEBUG logs.
    Aggressively truncates content. Never used when LOG_AI_CONTENT=false.
    """
    if not content:
        return "[SENSITIVE_DEBUG (empty)]"
    cleaned = content.strip().replace("\n", " ")
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + f"... [truncated total_len={len(content)}]"
    return f"[SENSITIVE_DEBUG: {cleaned}]"
