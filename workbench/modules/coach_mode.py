from __future__ import annotations

import datetime
import difflib
import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from backend.app.models.schemas import CoachOpeningAnalysisResult, CoachTurnResponse
from backend.app.prompts.coach import (
    build_coach_conversation_prompt,
    build_coach_opening_prompt,
)
from backend.app.prompts.coach_memory import build_coach_memory_update_prompt
from backend.app.services.ai.config import ModelRole
from workbench.state.models import (
    CoachMessageItem,
    CoachOpeningAnalysis,
    CoachState,
    DebateState,
    ReviewState,
)


class CoachModeEngine:
    """
    Isolated engine for Coach Mode:
    - Opening Analysis generation
    - Multi-turn coach conversations & phoneme tool loops
    - Long-term Coach Memory Markdown updates & diffs
    """

    @classmethod
    async def generate_opening_analysis(
        cls,
        coach_state: CoachState,
        live: bool = False,
    ) -> Tuple[CoachState, CoachOpeningAnalysis]:
        t_start = time.perf_counter()
        deb = coach_state.debate_state
        rev = coach_state.review_state

        topic = deb.topic if deb else (rev.topic if rev else "Debate Session")
        user_side = deb.user_side if deb else (rev.user_side if rev else "agree")
        opp_side = deb.opponent_side if deb else (rev.opponent_side if rev else "disagree")
        skill_name = deb.skill_name if deb else (rev.skill_name if rev else "Direct Refutation")
        diff = deb.difficulty if deb else (rev.difficulty if rev else "steady")

        transcript = deb.to_transcript_dicts() if deb else []

        review_dict = {
            "outcome": rev.outcome if rev else "undetermined",
            "stars": rev.mastery_stars if rev else 0,
            "technique": rev.score_technique.score if rev and rev.score_technique else 8,
            "grammar": rev.score_grammar.score if rev and rev.score_grammar else 8,
            "vocabulary": rev.score_vocabulary.score if rev and rev.score_vocabulary else 8,
            "delivery": rev.score_delivery.score if rev and rev.score_delivery else 8,
            "strongest_moment": rev.strongest_moment if rev else "Your speech stayed understandable across the exchange.",
            "improvement_opportunity": rev.improvement_opportunity if rev else "Use shorter sentences so each spoken idea lands clearly.",
            "language_feedback": rev.language_feedback if rev and rev.language_feedback else {},
            "has_sufficient_evidence": rev.evidence_assessment.has_sufficient_evidence if rev else True,
        }

        prompt_messages = build_coach_opening_prompt(
            topic=topic,
            user_side=user_side,
            opponent_side=opp_side,
            skill_name=skill_name,
            difficulty=diff,
            transcript=transcript,
            review=review_dict,
            coach_memory_markdown=coach_state.coach_memory_markdown,
        )

        coach_state.last_coach_prompt = prompt_messages

        if live:
            from backend.app.services.ai.gateway import ai_gateway
            opening_res = await ai_gateway._execute_structured_completion(
                role=ModelRole.LANGUAGE_ANALYSIS,
                messages=prompt_messages,
                schema_cls=CoachOpeningAnalysisResult,
                fallback_factory=lambda: CoachOpeningAnalysisResult(
                    overall_assessment="Here is the highest-value pattern in your spoken English from this session.",
                    most_important_strength=rev.strongest_moment if rev and rev.strongest_moment else "Intelligible delivery under pressure.",
                    highest_value_improvement=rev.improvement_opportunity if rev and rev.improvement_opportunity else "Keep spoken claims concise.",
                    concrete_example=transcript[0]["text"] if transcript else "Your argument",
                    evidence_turn_number=1,
                    suggested_quick_replies=["How should I phrase it?", "What should I practice?", "Let me try that again"],
                ),
            )
            raw_str = opening_res.model_dump_json(indent=2)
            coach_state.last_coach_raw = raw_str

            analysis = CoachOpeningAnalysis(
                overall_assessment=opening_res.overall_assessment,
                most_important_strength=opening_res.most_important_strength,
                highest_value_improvement=opening_res.highest_value_improvement,
                concrete_example=opening_res.concrete_example,
                evidence_turn_number=opening_res.evidence_turn_number,
                suggested_quick_replies=opening_res.suggested_quick_replies,
                recommended_audio_clip={
                    "turn_number": opening_res.evidence_turn_number or 1,
                    "what_to_notice": opening_res.highest_value_improvement,
                    "excerpt": opening_res.concrete_example or "Key phrase",
                },
            )
        else:
            # Deterministic mock opening analysis
            analysis = CoachOpeningAnalysis(
                overall_assessment="Your argument structure was clean and direct. The single highest-value spoken opportunity is keeping voiceless /θ/ crisp under pressure.",
                most_important_strength=rev.strongest_moment if rev and rev.strongest_moment else "Turn 2 refutation of budget assumptions.",
                highest_value_improvement="In words like [[pronounce:proportionally]] and [[pronounce:therefore]], place the tongue tip lightly between the upper and lower teeth so it doesn't soften into /s/.",
                concrete_example="Your claim assumes overall software budgets will expand proportionally...",
                evidence_turn_number=2,
                suggested_quick_replies=[
                    "How should I pronounce 'proportionally'?",
                    "Give me a 1-minute practice drill",
                    "Was my grammar clear in turn 3?",
                ],
                recommended_audio_clip={
                    "turn_number": 2,
                    "duration_sec": 16.2,
                    "what_to_notice": "Listen to the onset of 'proportionally'.",
                    "excerpt": "corporate IT budgets are constrained...",
                },
            )
            coach_state.last_coach_raw = analysis.model_dump_json(indent=2)

        dur_ms = round((time.perf_counter() - t_start) * 1000, 2)
        coach_state.last_latency_ms = dur_ms
        coach_state.opening_analysis = analysis

        # Append opening analysis message to thread
        coach_state.thread_messages.append(
            CoachMessageItem(
                sender="coach",
                message_type="opening_analysis",
                text=analysis.overall_assessment,
                structured_data=analysis.model_dump(),
            )
        )

        return coach_state, analysis

    @classmethod
    async def process_coach_turn(
        cls,
        coach_state: CoachState,
        user_message: str,
        live: bool = False,
    ) -> Tuple[CoachState, CoachMessageItem]:
        t_start = time.perf_counter()

        # 1. Record user message
        user_item = CoachMessageItem(
            sender="user",
            message_type="text",
            text=user_message.strip(),
        )
        coach_state.thread_messages.append(user_item)

        # 2. Build history and context
        deb = coach_state.debate_state
        rev = coach_state.review_state

        history_msgs = []
        for m in coach_state.thread_messages:
            history_msgs.append({
                "sender": m.sender,
                "text": m.text,
                "structured_data": m.structured_data,
            })

        debate_context = None
        if deb and rev:
            debate_context = {
                "topic": deb.topic,
                "user_side": deb.user_side,
                "opponent_side": deb.opponent_side,
                "skill_name": deb.skill_name,
                "outcome": rev.outcome,
                "stars": rev.mastery_stars,
                "has_sufficient_evidence": rev.evidence_assessment.has_sufficient_evidence,
                "score_technique": rev.score_technique.score if rev.score_technique else 8,
                "score_grammar": rev.score_grammar.score if rev.score_grammar else 8,
                "score_vocabulary": rev.score_vocabulary.score if rev.score_vocabulary else 8,
                "score_delivery": rev.score_delivery.score if rev.score_delivery else 8,
                "strongest_moment": rev.strongest_moment,
                "improvement_opportunity": rev.improvement_opportunity,
                "language_feedback": rev.language_feedback or {},
                "transcript": deb.to_transcript_dicts(),
            }

        prompt_messages = build_coach_conversation_prompt(
            thread_title=f"Review: {deb.topic if deb else 'Debate Practice'}",
            thread_type="debate_review",
            debate_context=debate_context,
            message_history=history_msgs[-10:],
            coach_memory_markdown=coach_state.coach_memory_markdown,
        )

        coach_state.last_coach_prompt = prompt_messages
        tool_call_trace: Optional[List[Dict[str, Any]]] = None

        if live:
            from backend.app.services.ai.gateway import ai_gateway

            def default_fallback():
                return CoachTurnResponse(
                    reply_text="Keep your spoken sentence concise: state the main assertion, pause briefly, then offer one supporting example.",
                    requested_tool=None,
                    tool_args=None,
                    evidence_card=None,
                    quick_replies=["How should I phrase it?", "What should I practice next?", "Let me try that again"],
                )

            coach_resp = await ai_gateway._execute_structured_completion(
                role=ModelRole.COACH,
                messages=prompt_messages,
                schema_cls=CoachTurnResponse,
                fallback_factory=default_fallback,
            )

            # Handle Tool Loop: get_phoneme_data
            if coach_resp.requested_tool == "get_phoneme_data":
                tool_call_trace = [{"tool": "get_phoneme_data", "args": coach_resp.tool_args}]
                phoneme_data = {
                    "phonemes": (deb.evidence[0].get("phonemes") if deb and deb.evidence else [{"sound": "θ", "word": "proportionally"}]),
                    "speech_metrics": {"duration_ms": 16200, "words_per_minute": 142},
                }
                tool_call_msg = {
                    "role": "assistant",
                    "content": json.dumps({"requested_tool": "get_phoneme_data", "tool_args": coach_resp.tool_args or {}}),
                }
                tool_res_msg = {
                    "role": "user",
                    "content": f"[Tool Result for get_phoneme_data]:\n{json.dumps(phoneme_data, indent=2)}\n\nNow provide your final coach feedback based on this acoustic evidence.",
                }
                updated_messages = list(prompt_messages) + [tool_call_msg, tool_res_msg]
                coach_resp = await ai_gateway._execute_structured_completion(
                    role=ModelRole.COACH,
                    messages=updated_messages,
                    schema_cls=CoachTurnResponse,
                    fallback_factory=lambda: coach_resp,
                )

            reply_text = coach_resp.reply_text
            quick_replies = coach_resp.quick_replies or []
            card_spec = coach_resp.evidence_card
            raw_str = coach_resp.model_dump_json(indent=2)
            coach_state.last_coach_raw = raw_str
        else:
            # Deterministic mock coach reply
            if "pronounce" in user_message.lower() or "drill" in user_message.lower():
                reply_text = (
                    "To articulate [[pronounce:proportionally]] cleanly: place your tongue tip gently between your upper and lower incisors on 'pro-POR-tion-al-ly'. "
                    "Release unvoiced air gently so it doesn't buzz like /z/ or hiss like /s/. "
                    "Try this drill: say 'a proportional share' three times slowly, pausing between each repetition."
                )
            else:
                reply_text = (
                    "In debate pressure, start with your core answer before justifying it. "
                    "Instead of qualifying upfront, say: 'Budgets are capped, so firms hire fewer juniors.' "
                    "That lands with immediate authority."
                )
            quick_replies = ["Let me try saying that", "How was my pacing?", "Give me another example"]
            card_spec = {
                "source_label": "Debate · Turn 2",
                "transcript_excerpt": "corporate IT budgets are constrained...",
                "what_to_notice": "Notice how the argument pivots quickly.",
            }
            raw_str = json.dumps({"reply": reply_text, "quick_replies": quick_replies}, indent=2)
            coach_state.last_coach_raw = raw_str

        dur_ms = round((time.perf_counter() - t_start) * 1000, 2)
        coach_state.last_latency_ms = dur_ms

        coach_msg = CoachMessageItem(
            sender="coach",
            message_type="evidence_card" if card_spec else "text",
            text=reply_text,
            structured_data={
                "quick_replies": [{"label": q, "prompt": q} for q in quick_replies],
                "evidence_card": card_spec,
            },
            tool_calls=tool_call_trace,
        )
        coach_state.thread_messages.append(coach_msg)
        return coach_state, coach_msg

    @classmethod
    async def update_coach_memory(
        cls,
        coach_state: CoachState,
        live: bool = False,
    ) -> Tuple[CoachState, str, Dict[str, Any]]:
        """
        Updates the long-term Coach Memory Markdown based on the review and debate findings,
        exposing the previous markdown, updated markdown, and visual diff.
        """
        t_start = time.perf_counter()
        deb = coach_state.debate_state
        rev = coach_state.review_state
        prev_md = coach_state.coach_memory_markdown or (
            "# Rebutio Coach Memory\n\n"
            "## User Preferences & Goals\n"
            "- User values concise arguments.\n\n"
            "## Historical Summary\n"
            "- Clean reasoning structure.\n\n"
            "## Recent Debates\n"
        )

        today = datetime.date.today().isoformat()
        debate_summary = {
            "session_id": deb.session_id if deb else (rev.session_id if rev else "sess-unknown"),
            "topic": deb.topic if deb else (rev.topic if rev else "Debate Topic"),
            "user_side": deb.user_side if deb else (rev.user_side if rev else "agree"),
            "outcome": rev.outcome if rev else "user_win",
            "stars": rev.mastery_stars if rev else 3,
            "has_sufficient_evidence": rev.evidence_assessment.has_sufficient_evidence if rev else True,
            "score_technique": rev.score_technique.score if rev and rev.score_technique else 9,
            "score_grammar": rev.score_grammar.score if rev and rev.score_grammar else 9,
            "score_vocabulary": rev.score_vocabulary.score if rev and rev.score_vocabulary else 8,
            "score_delivery": rev.score_delivery.score if rev and rev.score_delivery else 8,
            "strongest_moment": rev.strongest_moment if rev else "Direct refutation of premise in turn 2",
            "improvement_opportunity": rev.improvement_opportunity if rev else "Voiceless dental fricatives (/θ/) under pressure",
            "language_feedback": rev.language_feedback if rev else {},
            "transcript": deb.to_transcript_dicts() if deb else [],
        }

        prompt_messages = build_coach_memory_update_prompt(
            previous_memory_markdown=prev_md,
            debate_summary=debate_summary,
            current_date=today,
        )
        coach_state.last_coach_prompt = prompt_messages

        if live:
            from backend.app.services.ai.gateway import ai_gateway
            updated_md = await ai_gateway.update_coach_memory(
                messages=prompt_messages,
                previous_markdown=prev_md,
                debate_summary=debate_summary,
                current_date=today,
            )
        else:
            # Deterministic mock update appending new debate session
            session_entry = (
                f"\n### [{today}] Debate: {debate_summary['topic']}\n"
                f"- Stance: {debate_summary['user_side'].capitalize()} | Outcome: {debate_summary['outcome'].replace('_', ' ').title()} | Stars: {debate_summary['stars']}/3\n"
                f"- Technique ({debate_summary['score_technique']}/10): Refuted budget assumptions and argued apprenticeship bottlenecks directly.\n"
                f"- Delivery ({debate_summary['score_delivery']}/10): Maintained steady cadence averaging 138 WPM.\n"
                f"- Language & Grammar: Accurate complex sentence structures; minor softening on voiceless /θ/.\n"
                f"- Standout Moment: {debate_summary['strongest_moment']}\n"
                f"- Primary Focus For Next Time: {debate_summary['improvement_opportunity']}\n"
            )
            if "## Recent Debates" in prev_md:
                updated_md = prev_md.replace("## Recent Debates\n", f"## Recent Debates\n{session_entry}")
            else:
                updated_md = f"{prev_md.rstrip()}\n\n## Recent Debates\n{session_entry}"

        diff_lines = list(
            difflib.unified_diff(
                prev_md.splitlines(keepends=True),
                updated_md.splitlines(keepends=True),
                fromfile="previous_memory.md",
                tofile="updated_memory.md",
            )
        )
        diff_str = "".join(diff_lines)

        diff_summary = {
            "previous_length": len(prev_md),
            "updated_length": len(updated_md),
            "lines_added": sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++")),
            "lines_removed": sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---")),
            "diff": diff_str,
        }

        dur_ms = round((time.perf_counter() - t_start) * 1000, 2)
        coach_state.last_latency_ms = dur_ms
        coach_state.coach_memory_markdown = updated_md
        coach_state.memory_update_diff = diff_summary

        return coach_state, updated_md, diff_summary
