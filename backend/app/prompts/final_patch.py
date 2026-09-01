import json
from typing import List

FINAL_PATCH_SYSTEM_PROMPT = """You finalize Rebutio's speech-and-language analysis after the learner's final debate turn.

YOUR JOB:
Merge the final-turn evidence into the existing pre-final analysis without overreacting to one last sample.

RULES:
- Treat the pre-final analysis as a provisional summary, not unquestionable truth.
- Preserve recurring patterns supported across earlier turns unless the final turn materially contradicts them.
- Strengthen confidence or occurrence counts when the final turn repeats an existing pattern.
- Weaken or remove a finding when the final evidence shows the earlier conclusion was probably an artifact or overstatement.
- Do not create a major new pronunciation or grammar pattern from one isolated final-turn event unless the evidence is unusually clear and consequential.
- Distinguish pre-speaking planning delay from hesitation while speaking.
- Never infer pronunciation from transcript text alone.
- Accent variation is not an error unless a recurring realization affects intelligibility or a meaningful sound contrast.
- Keep the final top coaching points to the 1-2 changes with the highest practical value.
- If the combined evidence is clean, it is acceptable to report no meaningful pronunciation or grammar issue.

OUTPUT FORMAT:
Return strictly valid JSON matching the standard language-analysis schema:
{
  "pronunciation_findings": [...],
  "fluency_finding": {...},
  "grammar_finding": {...},
  "vocabulary_finding": {...},
  "clarity_finding": {...},
  "session_summary": "Final evidence-based synthesis.",
  "top_coaching_points": ["Top 1-2 actionable points"]
}
"""


def build_final_patch_prompt(
    pre_final_analysis: dict,
    final_turn_evidence: dict,
    topic: str,
    target_skill: str,
) -> List[dict]:
    payload = {
        "topic": topic,
        "target_skill": target_skill,
        "pre_final_analysis": pre_final_analysis,
        "final_turn_evidence": final_turn_evidence,
    }

    user_content = f"""Finalize the session language analysis using the final-turn evidence below.

{json.dumps(payload, indent=2)}

Update only what the combined evidence justifies. Return strictly valid JSON matching the standard schema.
"""
    return [
        {"role": "system", "content": FINAL_PATCH_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
