from enum import Enum
from typing import List, Optional
from pydantic import BaseModel
from backend.app.config import settings


class ModelRole(str, Enum):
    TRANSCRIPTION = "transcription"
    DEBATE_OPPONENT = "debate_opponent"
    SPEECH = "speech"
    LANGUAGE_ANALYSIS = "language_analysis"
    FINAL_LANGUAGE_PATCH = "final_language_patch"
    DEBATE_REVIEWER = "debate_reviewer"
    TOPIC_GENERATOR = "topic_generator"
    COACH = "coach"
    JSON_REPAIR = "json_repair"


class ProviderType(str, Enum):
    OPENROUTER = "openrouter"
    ROUTER_COM = "router_com"
    MOCK = "mock"


class RoleCandidate(BaseModel):
    provider: ProviderType
    model_id: str
    temperature: float = 0.7
    max_tokens: int = 2048
    reasoning_effort: Optional[str] = None  # "low", "medium", "high", "none"


class AICompletionResult(BaseModel):
    content: str
    reasoning: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    provider_request_id: Optional[str] = None
    finish_reason: Optional[str] = None
    resolved_model: Optional[str] = None
    upstream_provider: Optional[str] = None


def get_role_candidates(role: ModelRole) -> List[RoleCandidate]:
    candidates = []

    if role == ModelRole.TRANSCRIPTION:
        candidates.append(
            RoleCandidate(
                provider=ProviderType.OPENROUTER,
                model_id=settings.OPENROUTER_TRANSCRIPTION_MODEL,
            )
        )

    elif role == ModelRole.SPEECH:
        candidates.append(
            RoleCandidate(
                provider=ProviderType.OPENROUTER,
                model_id=settings.OPENROUTER_TTS_MODEL,
            )
        )

    elif role == ModelRole.DEBATE_OPPONENT:
        # Debate opponent: medium reasoning, 2048 token budget with GPT-5.6 Luna.
        # Visible replies are kept short through the prompt, not by starving the generation budget.
        if settings.RAMP_ROUTER_API_KEY and settings.ROUTER_DEBATE_MODEL:
            candidates.append(
                RoleCandidate(
                    provider=ProviderType.ROUTER_COM,
                    model_id=settings.ROUTER_DEBATE_MODEL,
                    temperature=0.8,
                    max_tokens=2048,
                    reasoning_effort="medium",
                )
            )
        candidates.append(
            RoleCandidate(
                provider=ProviderType.OPENROUTER,
                model_id=settings.OPENROUTER_DEBATE_MODEL,
                temperature=0.8,
                max_tokens=2048,
                reasoning_effort="medium",
            )
        )

    elif role == ModelRole.TOPIC_GENERATOR:
        # Topic generator: low reasoning, 2048 budget.
        if settings.RAMP_ROUTER_API_KEY and settings.ROUTER_TOPIC_MODEL:
            candidates.append(
                RoleCandidate(
                    provider=ProviderType.ROUTER_COM,
                    model_id=settings.ROUTER_TOPIC_MODEL,
                    temperature=0.9,
                    max_tokens=2048,
                    reasoning_effort="low",
                )
            )
        candidates.append(
            RoleCandidate(
                provider=ProviderType.OPENROUTER,
                model_id=settings.OPENROUTER_TOPIC_MODEL,
                temperature=0.9,
                max_tokens=2048,
                reasoning_effort="low",
            )
        )

    elif role == ModelRole.LANGUAGE_ANALYSIS:
        # Language analysis: medium reasoning, larger budget.
        if settings.RAMP_ROUTER_API_KEY and settings.ROUTER_ANALYSIS_MODEL:
            candidates.append(
                RoleCandidate(
                    provider=ProviderType.ROUTER_COM,
                    model_id=settings.ROUTER_ANALYSIS_MODEL,
                    temperature=0.3,
                    max_tokens=4096,
                    reasoning_effort="medium",
                )
            )
        candidates.append(
            RoleCandidate(
                provider=ProviderType.OPENROUTER,
                model_id=settings.OPENROUTER_ANALYSIS_MODEL,
                temperature=0.3,
                max_tokens=4096,
                reasoning_effort="medium",
            )
        )

    elif role == ModelRole.FINAL_LANGUAGE_PATCH:
        # Final language patch: low/medium reasoning.
        if settings.RAMP_ROUTER_API_KEY and settings.ROUTER_ANALYSIS_MODEL:
            candidates.append(
                RoleCandidate(
                    provider=ProviderType.ROUTER_COM,
                    model_id=settings.ROUTER_ANALYSIS_MODEL,
                    temperature=0.3,
                    max_tokens=3500,
                    reasoning_effort="low",
                )
            )
        candidates.append(
            RoleCandidate(
                provider=ProviderType.OPENROUTER,
                model_id=settings.OPENROUTER_FINAL_PATCH_MODEL,
                temperature=0.3,
                max_tokens=3500,
                reasoning_effort="low",
            )
        )

    elif role == ModelRole.DEBATE_REVIEWER:
        # Debate reviewer: medium reasoning, much larger budget.
        if settings.RAMP_ROUTER_API_KEY and settings.ROUTER_REVIEW_MODEL:
            candidates.append(
                RoleCandidate(
                    provider=ProviderType.ROUTER_COM,
                    model_id=settings.ROUTER_REVIEW_MODEL,
                    temperature=0.3,
                    max_tokens=4096,
                    reasoning_effort="medium",
                )
            )
        candidates.append(
            RoleCandidate(
                provider=ProviderType.OPENROUTER,
                model_id=settings.OPENROUTER_REVIEW_MODEL,
                temperature=0.3,
                max_tokens=4096,
                reasoning_effort="medium",
            )
        )

    elif role == ModelRole.COACH:
        # Coach: low reasoning, generous response budget with GPT-5.6 Luna.
        if settings.RAMP_ROUTER_API_KEY and (settings.ROUTER_COACH_MODEL or settings.ROUTER_ANALYSIS_MODEL):
            candidates.append(
                RoleCandidate(
                    provider=ProviderType.ROUTER_COM,
                    model_id=settings.ROUTER_COACH_MODEL or settings.ROUTER_ANALYSIS_MODEL,
                    temperature=0.7,
                    max_tokens=2500,
                    reasoning_effort="low",
                )
            )
        candidates.append(
            RoleCandidate(
                provider=ProviderType.OPENROUTER,
                model_id=settings.OPENROUTER_COACH_MODEL or settings.OPENROUTER_ANALYSIS_MODEL,
                temperature=0.7,
                max_tokens=2500,
                reasoning_effort="low",
            )
        )

    elif role == ModelRole.JSON_REPAIR:
        # JSON repair: no/minimal reasoning.
        if settings.RAMP_ROUTER_API_KEY and settings.ROUTER_ANALYSIS_MODEL:
            candidates.append(
                RoleCandidate(
                    provider=ProviderType.ROUTER_COM,
                    model_id=settings.ROUTER_ANALYSIS_MODEL,
                    temperature=0.0,
                    max_tokens=2048,
                    reasoning_effort="none",
                )
            )
        candidates.append(
            RoleCandidate(
                provider=ProviderType.OPENROUTER,
                model_id=settings.OPENROUTER_ANALYSIS_MODEL,
                temperature=0.0,
                max_tokens=2048,
                reasoning_effort="none",
            )
        )

    return candidates
