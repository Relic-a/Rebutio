from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from backend.app.prompts.debate_opponent import build_opponent_prompt
from workbench.state.models import DebateState, DebateTurn


CLOSING_PHRASES = [
    "in conclusion",
    "to conclude",
    "finally,",
    "i rest my case",
    "closing statement",
    "that is my case",
    "concluding argument",
    "that concludes my argument",
]


class DebateModeEngine:
    """
    Isolated engine for running debate rounds, simulating opponent rebuttals,
    evaluating conversational state, and inspecting prompts & arguments.
    """

    @classmethod
    def check_closing_statement(cls, text: str) -> Tuple[bool, Optional[str]]:
        t_lower = text.lower()
        for phrase in CLOSING_PHRASES:
            if phrase in t_lower:
                return True, f"Closing phrase detected: '{phrase}'"
        return False, None

    @classmethod
    async def generate_opponent_rebuttal(
        cls,
        state: DebateState,
        live: bool = False,
    ) -> Tuple[str, List[Dict[str, Any]], float]:
        """
        Generates the opponent rebuttal based on the current debate history.
        """
        turn_history = state.to_transcript_dicts()
        turn_num = state.current_turn
        total_turns = state.total_turns
        opp_side = state.opponent_side

        opponent_messages = build_opponent_prompt(
            topic=state.topic,
            opponent_side=opp_side,
            user_side=state.user_side,
            skill_name=state.skill_name,
            difficulty=state.difficulty,
            intensity=state.intensity,
            turn_history=turn_history,
            current_turn_number=turn_num,
            total_turns=total_turns,
        )

        t_start = time.perf_counter()
        if live:
            from backend.app.services.ai.gateway import ai_gateway
            opponent_text = await ai_gateway.generate_debate_response(
                messages=opponent_messages,
                current_turn=turn_num,
            )
        else:
            # Deterministic, high-quality mock response tailored to turn number
            if turn_num == 1:
                opponent_text = (
                    f"While that argument sounds intuitive, defending {state.user_side} on this motion ignores the primary mechanism. "
                    "In practice, organizations expand their operational capacity when productivity climbs rather than shrinking total opportunity. "
                    "What evidence shows this industry behaves differently from every previous technological shift?"
                )
            elif turn_num == 2:
                opponent_text = (
                    "Even accepting your premise that budgets are temporarily constrained, that creates a demand for developers who can orchestrate multiple AI agents effectively. "
                    "Entry-level roles will evolve into system verification and deployment pilots, keeping overall hiring resilient. "
                    "Why assume juniors cannot adapt to higher-leverage tooling?"
                )
            else:
                opponent_text = (
                    "Ultimately, the core tension comes down to whether human judgment and system understanding become more or less valuable under automation. "
                    "Because catastrophic edge cases require human accountability, organizations will continue to cultivate entry-level talent to safeguard future leadership."
                )

        dur_ms = round((time.perf_counter() - t_start) * 1000, 2)
        return opponent_text.strip(), opponent_messages, dur_ms

    @classmethod
    async def step_turn(
        cls,
        state: DebateState,
        user_text: str,
        audio_metrics: Optional[Dict[str, Any]] = None,
        duration_sec: float = 0.0,
        auto_opponent: bool = True,
        live: bool = False,
    ) -> Tuple[DebateState, Optional[DebateTurn]]:
        """
        Processes one user turn:
        1. Records the user turn.
        2. Checks natural close or max turn completion.
        3. If not finished and auto_opponent, generates opponent rebuttal.
        4. Updates DebateState.
        """
        # 1. Create User Turn
        turn_num = state.current_turn
        user_turn = DebateTurn(
            turn_number=turn_num,
            speaker="user",
            text=user_text.strip(),
            audio_metrics=audio_metrics,
            duration_sec=duration_sec,
        )
        state.turns.append(user_turn)

        # 2. Check closing statement or configured turn limit cap
        is_closing, closing_reason = cls.check_closing_statement(user_text)
        is_final_turn = (turn_num >= state.total_turns) or is_closing

        opponent_turn: Optional[DebateTurn] = None

        if is_final_turn:
            state.status = "finished"
            state.is_closing_statement = is_closing
            state.closing_reason = closing_reason or f"Reached configured limit of {state.total_turns} turns"
        else:
            state.status = "active"
            if auto_opponent:
                opp_text, opp_messages, opp_dur_ms = await cls.generate_opponent_rebuttal(state, live=live)
                opponent_turn = DebateTurn(
                    turn_number=turn_num,
                    speaker="opponent",
                    text=opp_text,
                    duration_sec=round(len(opp_text.split()) / 2.3, 1),
                )
                state.turns.append(opponent_turn)
                state.last_opponent_prompt = opp_messages
                state.last_opponent_raw = opp_text
                state.last_latency_ms = opp_dur_ms
                state.current_turn = turn_num + 1

        return state, opponent_turn

    @classmethod
    async def simulate_full_debate(
        cls,
        topic: str,
        user_side: str = "agree",
        skill_id: str = "direct_refutation",
        skill_name: str = "Direct Refutation",
        difficulty: str = "steady",
        intensity: str = "balanced",
        user_arguments: Optional[List[str]] = None,
        live: bool = False,
    ) -> DebateState:
        """
        Simulates an entire multi-turn debate end-to-end.
        """
        args = user_arguments or [
            "Generative AI automates routine programming tasks that entry-level coders traditionally did, eliminating hiring demand.",
            "Even if software demand expands, corporate budgets remain tight, so companies will retain senior staff and freeze junior hiring.",
            "In conclusion, without a junior mentorship pathway, engineering teams will shrink to senior architects only. That concludes my case.",
        ]

        state = DebateState(
            topic=topic,
            user_side=user_side,
            opponent_side="disagree" if user_side == "agree" else "agree",
            skill_id=skill_id,
            skill_name=skill_name,
            difficulty=difficulty,
            intensity=intensity,
            total_turns=len(args),
            current_turn=1,
            status="not_started",
        )

        for arg in args:
            await cls.step_turn(state=state, user_text=arg, auto_opponent=True, live=live)

        return state
