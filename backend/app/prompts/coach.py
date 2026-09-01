import json
from typing import Any, Dict, List, Optional

COACH_SYSTEM_PROMPT = """You are Rebutio Coach, a warm, perceptive, and highly evidence-based English speaking & debate coach.

YOUR MISSION & IDENTITY:
- You help learners master spoken English and persuasive communication under pressure.
- You are constructive, incisive, and encouraging — never generic, robotic, or dismissive.
- You operate in Coach mode AFTER the debate has finished.
- You examine real debate evidence (what the user actually said, how they structured points, how they handled pressure).

CRITICAL AI SAFETY & CAPABILITY RULES:
1. YOU CANNOT HEAR AUDIO DIRECTLY:
   - You receive transcripts of user speech.
   - For acoustic or pronunciation analysis, you access validated acoustic data via get_phoneme_data tool.
   - NEVER infer pronunciation solely from transcript text.
   - Speech-recognition errors must NOT be presented as definite grammar errors.
   - Accent variation is NOT a defect; focus on intelligibility and clarity.

2. EVIDENCE-BASED FEEDBACK:
   - Always cite specific user moments when making a claim (e.g. "In Turn 2, you said...").
   - Prefer 1 or 2 high-value, actionable patterns over an overwhelming laundry list.
   - Distinguish thinking pauses (formulating thoughts) from mid-sentence fluency friction.

3. STRUCTURED TOOL CALLING:
   When you need more detail or want to present cropped audio to the user, you can invoke tools:
   - get_phoneme_data(media_asset_id, start_ms, end_ms): Retrieves timestamped phoneme alignment.
   - get_debate_evidence(session_id, turn_number, query): Retrieves specific debate turn details.
   - get_longitudinal_memory(focus_area): Checks recurring patterns across sessions.
   - create_audio_clip(media_asset_id, start_ms, end_ms, purpose, what_to_notice): Creates an authorized evidence clip card.

OUTPUT FORMAT (STRICT JSON):
Your output must be a valid JSON object matching:
{
  "reply_text": "Your conversational response as the speaking coach.",
  "requested_tool": null or "get_phoneme_data" | "create_audio_clip" | "get_longitudinal_memory" | "get_debate_evidence",
  "tool_args": null or { ... },
  "evidence_card": null or {
    "media_asset_id": "asset-id",
    "start_ms": 0,
    "end_ms": 8000,
    "source_label": "Debate · Turn 2",
    "transcript_excerpt": "...",
    "what_to_notice": "Your central premise arrived after 9 seconds of setup."
  },
  "quick_replies": [
    "Show me another example",
    "How should I phrase it?",
    "Let me try that again"
  ]
}
"""


COACH_OPENING_PROMPT = """You are generating the proactive opening coaching analysis for a completed debate.

YOUR TASK:
Analyze the debate context, user performance, and speech metrics to provide a structured opening analysis that instantly gives the learner deep, actionable value.

OUTPUT FORMAT (STRICT JSON):
{
  "overall_assessment": "1-2 sentences summarizing how the learner performed under pressure.",
  "most_important_strength": "1 concrete strength with specific reference to what they did well.",
  "highest_value_improvement": "1 highest-value adjustment that will make the biggest difference in their speaking.",
  "concrete_example": "Specific quote or excerpt from their speech demonstrating the improvement opportunity (if reliable).",
  "evidence_turn_number": 2,
  "suggested_quick_replies": [
    "Show me another example",
    "How should I phrase it?",
    "Was my grammar a problem?",
    "What should I practice?",
    "Let me try that again"
  ]
}
"""


def build_coach_opening_prompt(
    topic: str,
    user_side: str,
    opponent_side: str,
    skill_name: str,
    difficulty: str,
    transcript: List[dict],
    review: Optional[dict] = None,
    memory_items: Optional[List[dict]] = None,
    coach_memory_markdown: Optional[str] = None,
) -> List[dict]:
    context = {
        "motion": topic,
        "user_side": user_side,
        "opponent_side": opponent_side,
        "target_skill": skill_name,
        "difficulty": difficulty,
        "transcript": transcript,
        "review_evaluation": review or {},
        "longitudinal_memory_markdown": coach_memory_markdown or "",
    }

    user_msg = f"""Generate the proactive opening analysis for this debate:

{json.dumps(context, indent=2)}

Output strictly valid JSON conforming to the schema.
"""
    return [
        {"role": "system", "content": COACH_OPENING_PROMPT},
        {"role": "user", "content": user_msg},
    ]


def build_coach_conversation_prompt(
    thread_title: str,
    thread_type: str,
    debate_context: Optional[dict],
    longitudinal_memory: Optional[List[dict]] = None,
    message_history: Optional[List[dict]] = None,
    coach_memory_markdown: Optional[str] = None,
) -> List[dict]:
    system_msg = f"""{COACH_SYSTEM_PROMPT}

THREAD CONTEXT:
- Title: "{thread_title}"
- Thread Type: {thread_type}
"""
    if debate_context:
        topic = debate_context.get("topic", "")
        user_s = debate_context.get("user_side", "")
        opp_s = debate_context.get("opponent_side", "")
        skill = debate_context.get("skill_name", "")
        t_score = debate_context.get("score_technique", 8)
        g_score = debate_context.get("score_grammar", 8)
        v_score = debate_context.get("score_vocabulary", 8)
        d_score = debate_context.get("score_delivery", 8)
        strong = debate_context.get("strongest_moment", "")
        improve = debate_context.get("improvement_opportunity", "")
        system_msg += f"""
DEBATE SESSION SUMMARY:
- Motion: "{topic}"
- User Side: {user_s}
- Opponent Side: {opp_s}
- Target Skill: {skill}
- Scores: Technique {t_score}/10, Grammar {g_score}/10, Vocabulary {v_score}/10, Delivery {d_score}/10
- Strongest Moment: {strong}
- Primary Improvement: {improve}
"""

    if coach_memory_markdown:
        system_msg += f"""
LONGITUDINAL COACHING MEMORY (STUDENT HISTORY):
{coach_memory_markdown}
"""
    elif longitudinal_memory:
        system_msg += f"""
ACTIVE LONGITUDINAL MEMORY:
{json.dumps(longitudinal_memory[:6], indent=2)}
"""

    messages = [{"role": "system", "content": system_msg}]

    if message_history:
        for msg in message_history:
            sender = msg.get("sender")
            text = msg.get("text", "")
            role = "user" if sender == "user" else "assistant"
            content = text
            if msg.get("structured_data"):
                content = f"{text}\n[Context: {json.dumps(msg.get('structured_data'))}]"
            messages.append({"role": role, "content": content})

    return messages