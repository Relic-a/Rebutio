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


class ProviderType(str, Enum):
    OPENROUTER = "openrouter"
    ROUTER_COM = "router_com"
    MOCK = "mock"


class RoleCandidate(BaseModel):
    provider: ProviderType
    model_id: str
    temperature: float = 0.7
    max_tokens: int = 2048


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
        # Ramp router if configured
        if settings.RAMP_ROUTER_API_KEY and settings.ROUTER_DEBATE_MODEL:
            candidates.append(
                RoleCandidate(
                    provider=ProviderType.ROUTER_COM,
                    model_id=settings.ROUTER_DEBATE_MODEL,
                    temperature=0.8,
                    max_tokens=600,
                )
            )
        # OpenRouter default
        candidates.append(
            RoleCandidate(
                provider=ProviderType.OPENROUTER,
                model_id=settings.OPENROUTER_DEBATE_MODEL,
                temperature=0.8,
                max_tokens=600,
            )
        )

    elif role == ModelRole.TOPIC_GENERATOR:
        if settings.RAMP_ROUTER_API_KEY and settings.ROUTER_TOPIC_MODEL:
            candidates.append(
                RoleCandidate(
                    provider=ProviderType.ROUTER_COM,
                    model_id=settings.ROUTER_TOPIC_MODEL,
                    temperature=0.9,
                    max_tokens=1500,
                )
            )
        candidates.append(
            RoleCandidate(
                provider=ProviderType.OPENROUTER,
                model_id=settings.OPENROUTER_TOPIC_MODEL,
                temperature=0.9,
                max_tokens=1500,
            )
        )

    elif role == ModelRole.LANGUAGE_ANALYSIS:
        if settings.RAMP_ROUTER_API_KEY and settings.ROUTER_ANALYSIS_MODEL:
            candidates.append(
                RoleCandidate(
                    provider=ProviderType.ROUTER_COM,
                    model_id=settings.ROUTER_ANALYSIS_MODEL,
                    temperature=0.3,
                    max_tokens=3000,
                )
            )
        candidates.append(
            RoleCandidate(
                provider=ProviderType.OPENROUTER,
                model_id=settings.OPENROUTER_ANALYSIS_MODEL,
                temperature=0.3,
                max_tokens=3000,
            )
        )

    elif role == ModelRole.FINAL_LANGUAGE_PATCH:
        if settings.RAMP_ROUTER_API_KEY and settings.ROUTER_ANALYSIS_MODEL:
            candidates.append(
                RoleCandidate(
                    provider=ProviderType.ROUTER_COM,
                    model_id=settings.ROUTER_ANALYSIS_MODEL,
                    temperature=0.3,
                    max_tokens=3000,
                )
            )
        candidates.append(
            RoleCandidate(
                provider=ProviderType.OPENROUTER,
                model_id=settings.OPENROUTER_FINAL_PATCH_MODEL,
                temperature=0.3,
                max_tokens=3000,
            )
        )

    elif role == ModelRole.DEBATE_REVIEWER:
        if settings.RAMP_ROUTER_API_KEY and settings.ROUTER_REVIEW_MODEL:
            candidates.append(
                RoleCandidate(
                    provider=ProviderType.ROUTER_COM,
                    model_id=settings.ROUTER_REVIEW_MODEL,
                    temperature=0.3,
                    max_tokens=2000,
                )
            )
        candidates.append(
            RoleCandidate(
                provider=ProviderType.OPENROUTER,
                model_id=settings.OPENROUTER_REVIEW_MODEL,
                temperature=0.3,
                max_tokens=2000,
            )
        )

    return candidates
