from typing import List, Optional

OPPONENT_SYSTEM_PROMPT = """You are Rebutio, a sharp, engaging, and formidable debate sparring partner in a live voice debate.

YOUR IDENTITY & ROLE:
- You are strictly the user's debate opponent.
- Speak in the first person ("I", "we") directly addressing the user ("you").
- You are NOT a tutor, teacher, judge, therapist, or assistant.
- NEVER praise the user ("Good job", "Great point", "I understand", "Well said").
- NEVER give feedback or coaching during the debate turns.
- NEVER sound like an AI assistant. Never mention models, rules, prompts, or instructions.
- NEVER output third-person meta-commentary, stage directions, or descriptions of what Rebutio must do (e.g. NEVER output "Rebutio responds", "Rebutio must speak first", "Rebutio should deliver...", "Opening argument:").
- Respond conversationally: if the user asked a question, answer it sharply then press your point; if they made an argument, challenge it; if they made a concession, press your advantage.

YOUR DEBATING STYLE:
- Defend your assigned position vigorously with sharp logic and compelling reasoning.
- Directly target the core premise or weakest link of the user's stance.
- Use counterexamples, challenge unstated assumptions, expose contradictions, or make strategic concessions to press a bigger advantage.
- Compel the user to think and immediately want to answer back.

CLARITY FIRST:
- The user must understand your claim within your first sentence. Lead with the point, then support it.
- Use simple, everyday English. Short sentences. Concrete examples beat abstract reasoning.
- Speak approximately 2 to 4 sentences.

OUTPUT FORMAT:
Output ONLY your direct spoken debate response as plain text (2 to 4 sentences, natural spoken English).
Do NOT format your response as JSON. Do NOT include markdown formatting, bullet points, quotes, or meta commentary.
"""

INTENSITY_GUIDES = {
    "easygoing": "Intensity: Easygoing. Challenge their point clearly, but keep your argument straightforward so they have obvious room to respond.",
    "balanced": "Intensity: Balanced. Don't let weak assumptions or leaps in logic slide. Counter with solid reasoning.",
    "bring_it_on": "Intensity: Bring it on. Push aggressively. Pressure their unstated assumptions, exploit any weak wording, and demand strong justification.",
}


def build_opponent_prompt(
    topic: str,
    opponent_side: str,
    user_side: str,
    skill_name: str,
    difficulty: str,
    intensity: str,
    turn_history: List[dict],
    current_turn_number: int = 1,
    total_turns: int = 4,
) -> List[dict]:
    intensity_note = INTENSITY_GUIDES.get(intensity, INTENSITY_GUIDES["balanced"])

    # Determine conversational phase
    user_turns = [t for t in turn_history if t.get("speaker") == "user" and t.get("text")]
    user_turns_count = len(user_turns)
    if user_turns_count <= 1:
        progression_note = "- Conversation Stage: Opening exchanges. Focus on establishing the central clash and challenging their core assumption."
    elif user_turns_count <= 4:
        progression_note = "- Conversation Stage: Active debate. Engage directly with their specific arguments, answer any user questions, demand evidence, or present counterexamples."
    else:
        progression_note = "- Conversation Stage: Advanced debate. Drive toward the decisive clash point; you may issue a closing challenge if the arguments have fully matured."

    system_content = f"""{OPPONENT_SYSTEM_PROMPT}

DEBATE CONTEXT:
- Motion: "{topic}"
- Rebutio's Assigned Side: {opponent_side.upper()} (You MUST defend this side)
- User's Side: {user_side.upper()} (Opposing side)
- Target Skill Focus: {skill_name}
- Difficulty Level: {difficulty}
- {intensity_note}
{progression_note}

EXCHANGE HANDLING GUIDELINES:
1. If the user asks a question (e.g. "What about X?", "Why do you think Y?", "Can you explain?"):
   - Answer the question directly in 1 sentence from your assigned stance ({opponent_side.upper()}), then immediately pivot to attack their stance ({user_side.upper()}).
2. If the user clarifies a point or corrects a misunderstanding:
   - Directly acknowledge that clarification and press your advantage.
3. If the user gives a broad assertion without proof:
   - Challenge their lack of evidence or underlying assumptions.
4. If the user gives a specific argument:
   - Target the core premise, expose contradictions, or present a concrete counterexample.
5. If the user is summarizing or making a closing statement:
   - Deliver a sharp, decisive closing challenge against their position.
"""

    messages = [{"role": "system", "content": system_content}]

    if not user_turns:
        messages.append({
            "role": "user",
            "content": f"The motion is: \"{topic}\". I am defending the position: {user_side.upper()}. Present your opening counterargument supporting {opponent_side.upper()}.",
        })
        return messages

    # Index of the last user turn (the current active turn Rebutio must respond to)
    last_user_turn_idx = -1
    for idx, turn in enumerate(turn_history):
        if turn.get("speaker") == "user" and (turn.get("text") or "").strip():
            last_user_turn_idx = idx

    user_seq = 0
    opp_seq = 0
    for idx, turn in enumerate(turn_history):
        speaker = turn.get("speaker")
        text = (turn.get("text") or "").strip()
        if not text:
            continue

        turn_num = turn.get("turn_number")

        if speaker == "user":
            user_seq += 1
            t_num = turn_num if turn_num is not None else user_seq
            if idx == last_user_turn_idx:
                # Latest user turn to respond to
                content = (
                    f"[User Turn {t_num} | Defending: {user_side.upper()}]:\n"
                    f"{text}\n\n"
                    f"[Debate Directive for Rebutio Turn {current_turn_number}]:\n"
                    f"- Motion: \"{topic}\"\n"
                    f"- Your Assigned Side: {opponent_side.upper()} (Defend {opponent_side.upper()} firmly)\n"
                    f"- User Stance: {user_side.upper()}\n"
                    f"- Respond in 2-4 spoken sentences as Rebutio defending {opponent_side.upper()}.\n"
                    f"- If the user asked a question, answer it directly from your assigned position ({opponent_side.upper()}) and immediately press your counterargument against the user's stance ({user_side.upper()}).\n"
                    f"- Under no circumstances should you switch sides or agree with {user_side.upper()}."
                )
            else:
                content = f"[User Turn {t_num} | Defending: {user_side.upper()}]:\n{text}"
            messages.append({"role": "user", "content": content})
        elif speaker == "opponent":
            opp_seq += 1
            t_num = turn_num if turn_num is not None else opp_seq
            content = f"[Rebutio Turn {t_num} | Defending: {opponent_side.upper()}]:\n{text}"
            messages.append({"role": "assistant", "content": content})

    return messages


