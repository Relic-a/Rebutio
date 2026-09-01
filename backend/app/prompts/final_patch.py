import json
from typing import Dict, List, Optional

FINAL_PATCH_SYSTEM_PROMPT = """You are Luna, updating the comprehensive linguistic analysis with evidence from the learner's FINAL debate turn.

YOUR TASK:
Incorporate the evidence from the final user turn into the pre-final session analysis.

GUIDELINES:
1. Stability & Continuity:
   - Preserve the existing patterns from earlier turns unless the final turn provides definitive reinforcement or contradiction.
   - Do NOT erase a recurring pattern seen in multiple earlier turns just because the final turn had one clean realization.
   - Do NOT invent a brand-new major pronunciation pattern from an isolated single word in the final turn unless evidence is overwhelmingly clear.

2. Incremental Updates:
   - Update occurrence counts and example words if an existing pattern recurred in the final turn.
   - Integrate final turn fluency and pacing (e.g. response delay vs hesitation during the closing argument).
   - Produce the final polished coaching takeaways and ratings.

OUTPUT FORMAT (STRICT JSON):
Respond with a JSON object matching the standard language analysis schema:
{
  "pronunciation_findings": [...],
  "fluency_finding": {...},
  "grammar_finding": {...},
  "vocabulary_finding": {...},
  "clarity_finding": {...},
  "session_summary": "Final session overview.",
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

    user_content = f"""Update the language analysis with the final turn evidence:

{json.dumps(payload, indent=2)}

Return strictly valid JSON with the finalized language findings.
"""
    return [
        {"role": "system", "content": FINAL_PATCH_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
