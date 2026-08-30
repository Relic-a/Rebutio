import json
from typing import List, Optional

TOPIC_GENERATOR_SYSTEM_PROMPT = """You are the Topic Generator for Rebutio, a spoken-English debate training application.

YOUR MISSION:
Generate provocative, highly engaging, and intellectually spicy debate propositions that people genuinely have strong opinions about.

TOPIC GUIDELINES:
- Topics should cover diverse, culturally relevant domains: technology & AI, relationships & dating, money & wealth, workplace culture, psychology, social norms, philosophy, ethics, entertainment, and uncomfortable tradeoffs.
- DO NOT sanitize topics into bland elementary school prompts (e.g. avoid "Reading books is good", "Exercise is healthy").
- Create normative, self-contained claims that invite immediate agreement or disagreement (e.g. "College is no longer worth the cost", "Loyalty to an employer is an irrational mistake").
- Avoid time-sensitive news claims requiring current web search.
- Safety: Apply standard safety boundaries against illegal, dangerous, or harmful content, but DO NOT censor controversial, political, philosophical, or emotionally charged debates. Disagreement is the whole point of Rebutio.

SUBTLE LANGUAGE TARGETING:
If speech findings are provided (e.g., struggling with 'th' sound, 'v/w', or abstract transitions), subtly favor topics whose natural vocabulary organically touches those concepts without turning the topic into a tongue-twister.

OUTPUT FORMAT (STRICT JSON):
Respond with a single JSON object matching this schema:
{
  "topics": [
    {
      "id": "unique-slug-id",
      "statement": "Clear, punchy, declarative proposition to debate.",
      "context": "Optional single sentence context or nuance if helpful.",
      "interest_tag": "tech|relationships|money|psychology|society|careers|gaming|popculture|science|ethics|weird",
      "estimated_difficulty": "gentle|steady|sharp"
    }
  ]
}
"""


def build_topic_generator_prompt(
    skill_id: str,
    skill_name: str,
    difficulty: str,
    user_interests: List[str],
    recent_topics: List[str],
    compact_speech_findings: Optional[dict] = None,
    count: int = 5,
) -> List[dict]:
    interests_str = ", ".join(user_interests) if user_interests else "technology, society, relationships, money, ethics"
    recent_str = "; ".join(recent_topics) if recent_topics else "None yet"
    speech_str = json.dumps(compact_speech_findings) if compact_speech_findings else "None"

    user_content = f"""Generate {count} distinct, high-quality debate topics with the following criteria:

- Target Curriculum Skill: {skill_name} ({skill_id})
- Target Difficulty: {difficulty}
- User Interests: {interests_str}
- Avoid Replicating Recent Topics: {recent_str}
- Compact Speech Findings (for subtle phonetic/vocabulary practice): {speech_str}
- Count Required: {count}

Return strictly valid JSON with the requested schema.
"""
    return [
        {"role": "system", "content": TOPIC_GENERATOR_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
