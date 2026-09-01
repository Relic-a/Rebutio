import json
import pytest
from unittest.mock import AsyncMock, patch

from backend.app.models.schemas import (
    DebateReviewerResult,
    GeneratedTopicsResponse,
    MainLanguageAnalysisResult,
    StructuredClarityFinding,
    StructuredFluencyFinding,
    StructuredGrammarFinding,
    StructuredPronunciationFinding,
    StructuredVocabularyFinding,
)
from backend.app.config import settings
from backend.app.persistence.db import init_db
from backend.app.services.ai.config import AICompletionResult
from backend.app.services.ai.gateway import ai_gateway
from backend.app.services.ai.openrouter import openrouter_client
from backend.app.services.modal.client import modal_speech_client


_db_initialized = False


@pytest.fixture(autouse=True)
async def initialize_test_database():
    """
    Ensures SQLite tables and columns are initialized once for test sessions.
    """
    global _db_initialized
    if not _db_initialized:
        await init_db()
        _db_initialized = True


@pytest.fixture(autouse=True)
def mock_all_external_ai_services(monkeypatch):
    """
    Global autouse fixture to guarantee tests NEVER make live external network calls
    to OpenRouter, Router.com, Modal, or third-party AI services.
    Saves API costs, prevents rate-limits, and makes test execution instantaneous.
    """
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH_BYPASS", True)
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "test-mock-openrouter-key")
    monkeypatch.setattr(openrouter_client, "api_key", "test-mock-openrouter-key")
    monkeypatch.setattr(ai_gateway.openrouter, "api_key", "test-mock-openrouter-key")

    async def mock_openrouter_chat_raw(messages, model, temperature=0.7, max_tokens=1024, response_format_json=False):
        # Infer role/type from messages
        first_content = messages[0]["content"] if messages else ""
        
        if "LANGUAGE ANALYSIS ENGINE" in first_content or "FINAL PATCH" in first_content:
            sample_analysis = MainLanguageAnalysisResult(
                pronunciation_findings=[],
                fluency_finding=StructuredFluencyFinding(
                    summary="Fluent delivery throughout.",
                    trend="steady",
                    hesitation_vs_thinking_note="Quick planning time.",
                    score=85,
                ),
                grammar_finding=StructuredGrammarFinding(
                    summary="Clean grammar structure.",
                    recurring_pattern=None,
                    examples=[],
                    reportable=False,
                ),
                vocabulary_finding=StructuredVocabularyFinding(
                    summary="Clear debate vocabulary.",
                    examples=[],
                    suggested_alternatives=[],
                ),
                clarity_finding=StructuredClarityFinding(
                    summary="Point was intelligible and directly addressed the prompt.",
                    score=88,
                ),
                session_summary="Completed session with articulate delivery.",
                top_coaching_points=["Keep challenging opposing premises."],
            )
            content = sample_analysis.model_dump_json()

        elif "INDEPENDENT DEBATE REVIEWER" in first_content:
            sample_review = DebateReviewerResult(
                outcome="user_win",
                target_skill_demonstrated=True,
                mastery_stars=2,
                mastery_note="You addressed the counterargument directly.",
                skill_summary="Completed all turns under the target skill focus.",
                argument_strength="You challenged their main premise clearly.",
                argument_improvement="Push on unstated assumptions next time.",
                strategic_insight="Their argument relied on correlation over causation.",
            )
            content = sample_review.model_dump_json()

        elif "TOPIC GENERATOR" in first_content:
            sample_topics = GeneratedTopicsResponse(
                topics=[
                    {
                        "id": "topic-gen-1",
                        "statement": "College is no longer worth the cost.",
                        "context": "Tuition costs versus credentials.",
                        "interest_tag": "careers",
                        "estimated_difficulty": "gentle",
                    }
                ]
            )
            content = sample_topics.model_dump_json()

        elif "memory curator for Rebutio Coach" in first_content or "COACH MEMORY" in first_content:
            sample_memory = """# Rebutio Coach Memory

## User Preferences & Goals
- Focus: Structure arguments clearly.

## Historical Summary
- No historical debate summaries yet.

## Recent Debates
### [2026-08-31] Debate: Social Media Impact
- Stance: Agree | Outcome: User Win | Stars: 2/3
- Technique (8/10): Challenged opposing assumptions.
- Delivery (8/10): Confident pacing.
- Standout Moment: Maintained strong counterpoints.
- Primary Focus For Next Time: State thesis earlier.
"""
            content = sample_memory

        else:
            # Spoken debate opponent argument (2-4 sentences)
            content = "While technology provides instant communication, we must distinguish between speed and depth. Real friendships require shared physical vulnerability that screens inherently diminish."

        return AICompletionResult(
            content=content,
            input_tokens=150,
            output_tokens=45,
            provider_request_id="mock-gen-test",
            finish_reason="stop",
            resolved_model=model,
            upstream_provider="mock",
        )

    async def mock_stt(audio_bytes, audio_format="webm", model=None):
        return "I maintain my position based on the evidence presented."

    async def mock_tts(text, voice=None, model=None):
        # 44-byte standard empty WAV container header
        return b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"

    async def mock_modal_phonemes(audio_bytes, audio_format="webm", client_response_delay_ms=0):
        return {
            "audio_duration_ms": 1500,
            "phonemes": [{"phone": "DH", "start_ms": 0, "end_ms": 120}],
            "speech_metrics": {
                "total_phonemes": 1,
                "in_speech_gaps_count": 0,
                "total_in_speech_pause_duration_ms": 0,
                "first_phone_offset_ms": 0,
                "last_phone_end_ms": 120,
            },
            "client_response_delay_ms": client_response_delay_ms,
        }

    monkeypatch.setattr(ai_gateway.openrouter, "chat_completion_raw", mock_openrouter_chat_raw)
    monkeypatch.setattr(ai_gateway.openrouter, "chat_completion", lambda *a, **kw: mock_openrouter_chat_raw(*a, **kw))
    monkeypatch.setattr(ai_gateway.openrouter, "transcribe_audio", mock_stt)
    monkeypatch.setattr(ai_gateway.openrouter, "synthesize_speech", mock_tts)

    monkeypatch.setattr(ai_gateway.router_com, "chat_completion_raw", mock_openrouter_chat_raw)
    monkeypatch.setattr(ai_gateway.router_com, "chat_completion", lambda *a, **kw: mock_openrouter_chat_raw(*a, **kw))

    monkeypatch.setattr(modal_speech_client, "analyze_phonemes", mock_modal_phonemes)
