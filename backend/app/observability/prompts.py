"""
Central prompt version registry.
Provides stable explicit names and versions for all LLM prompt templates across Rebutio.
"""

from typing import Dict

PROMPT_VERSIONS: Dict[str, str] = {
    "debate_opponent": "debate_opponent:v2",
    "topic_generator": "topic_generator:v2",
    "language_analysis": "language_analysis:v2",
    "final_language_patch": "final_language_patch:v2",
    "debate_reviewer": "debate_reviewer:v2",
    "coach": "coach:v2",
    "coach_memory": "coach_memory:v2",
}


def get_prompt_version(template_name: str) -> str:
    """Returns the stable version string for a given prompt template name."""
    return PROMPT_VERSIONS.get(template_name, f"{template_name}:v1")
