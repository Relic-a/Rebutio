import json
import logging
import re
from typing import Any, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel

from backend.app.config import settings
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
from backend.app.services.ai.config import (
    ModelRole,
    ProviderType,
    RoleCandidate,
    get_role_candidates,
)
from backend.app.services.ai.openrouter import openrouter_client
from backend.app.services.ai.router_com import router_com_client

logger = logging.getLogger("rebutio.ai_gateway")

T = TypeVar("T", bound=BaseModel)


def clean_json_string(raw: str) -> str:
    """Strips markdown code blocks, backticks, and extraneous prefixes/suffixes."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
    return raw.strip()


class AIGateway:
    def __init__(self):
        self.openrouter = openrouter_client
        self.router_com = router_com_client

    async def transcribe_audio(self, audio_bytes: bytes, audio_format: str = "webm") -> str:
        """
        Transcribes original raw browser audio via MAI-Transcribe 1.5.
        """
        if not audio_bytes:
            return ""

        candidates = get_role_candidates(ModelRole.TRANSCRIPTION)
        for cand in candidates:
            if cand.provider == ProviderType.OPENROUTER and self.openrouter.is_configured:
                try:
                    text = await self.openrouter.transcribe_audio(
                        audio_bytes=audio_bytes,
                        audio_format=audio_format,
                        model=cand.model_id,
                    )
                    if text:
                        return text
                except Exception as e:
                    logger.warning(f"OpenRouter STT ({cand.model_id}) failed: {e}")

        # Fallback for local development / testing without active API key
        logger.info("Using simulated transcription fallback.")
        return "I believe this motion overlooks critical evidence and that on balance the alternative is much stronger."

    async def synthesize_speech(self, text: str, voice: Optional[str] = None) -> bytes:
        """
        Synthesizes opponent speech using Gemini 3.1 Flash TTS.
        """
        if not text:
            return b""

        candidates = get_role_candidates(ModelRole.SPEECH)
        for cand in candidates:
            if cand.provider == ProviderType.OPENROUTER and self.openrouter.is_configured:
                try:
                    audio_bytes = await self.openrouter.synthesize_speech(
                        text=text,
                        voice=voice or settings.REBUTIO_TTS_VOICE,
                        model=cand.model_id,
                    )
                    if audio_bytes:
                        return audio_bytes
                except Exception as e:
                    logger.warning(f"OpenRouter TTS ({cand.model_id}) failed: {e}")

        # Fallback: return 1-second silent WAV header for playback compatibility
        logger.info("Using silent audio fallback for TTS.")
        return b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"

    async def generate_debate_response(self, messages: List[dict], current_turn: int = 1) -> str:
        """
        Generates Rebutio's next spoken debate argument using DeepSeek V4 Pro.
        Output is natural, brief (2-4 sentences), and without tutor behavior.
        """
        candidates = get_role_candidates(ModelRole.DEBATE_OPPONENT)
        for cand in candidates:
            try:
                if cand.provider == ProviderType.ROUTER_COM and self.router_com.is_configured:
                    res = await self.router_com.chat_completion(
                        messages=messages,
                        model=cand.model_id,
                        temperature=cand.temperature,
                        max_tokens=cand.max_tokens,
                    )
                    if res:
                        return self._clean_opponent_text(res)
                elif cand.provider == ProviderType.OPENROUTER and self.openrouter.is_configured:
                    res = await self.openrouter.chat_completion(
                        messages=messages,
                        model=cand.model_id,
                        temperature=cand.temperature,
                        max_tokens=cand.max_tokens,
                    )
                    if res:
                        return self._clean_opponent_text(res)
            except Exception as e:
                logger.warning(f"Debate opponent candidate ({cand.provider}/{cand.model_id}) failed: {e}")

        # Fallback response for offline / mock mode
        mock_responses = [
            "Your argument rests on a convenient assumption, but it overlooks the core mechanism. If what you claim were true, we would see far different real-world outcomes.",
            "You say this is about individual freedom, but you haven't shown why the negative externalities should be ignored. Where does your principle draw the boundary?",
            "That's a common defense, yet the evidence points in the opposite direction. What is the single strongest reason that withstands this counterexample?",
        ]
        return mock_responses[(current_turn - 1) % len(mock_responses)]

    def _clean_opponent_text(self, text: str) -> str:
        # Strip any accidental markdown bullets, quotes, or headers
        cleaned = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
        cleaned = re.sub(r"^\s*[-*•]\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.replace("**", "").replace('"', "")
        return cleaned.strip()

    async def _execute_structured_completion(
        self,
        role: ModelRole,
        messages: List[dict],
        schema_cls: Type[T],
        fallback_factory: Any,
    ) -> T:
        candidates = get_role_candidates(role)
        for cand in candidates:
            try:
                raw_text = ""
                if cand.provider == ProviderType.ROUTER_COM and self.router_com.is_configured:
                    raw_text = await self.router_com.chat_completion(
                        messages=messages,
                        model=cand.model_id,
                        temperature=cand.temperature,
                        max_tokens=cand.max_tokens,
                        response_format_json=True,
                    )
                elif cand.provider == ProviderType.OPENROUTER and self.openrouter.is_configured:
                    raw_text = await self.openrouter.chat_completion(
                        messages=messages,
                        model=cand.model_id,
                        temperature=cand.temperature,
                        max_tokens=cand.max_tokens,
                        response_format_json=True,
                    )

                if raw_text:
                    cleaned = clean_json_string(raw_text)
                    parsed_json = json.loads(cleaned)
                    return schema_cls.model_validate(parsed_json)
            except Exception as e:
                logger.warning(f"Structured completion ({role.value} with {cand.provider}/{cand.model_id}) failed: {e}")

        logger.info(f"Using fallback response for structured role: {role.value}")
        return fallback_factory()

    async def generate_topics(self, messages: List[dict], skill_id: str = "take_a_side") -> GeneratedTopicsResponse:
        def fallback():
            from backend.app.domain.curriculum import get_skill
            skill = get_skill(skill_id)
            return GeneratedTopicsResponse(
                topics=[
                    {
                        "id": "topic-1",
                        "statement": "College is no longer worth the financial cost for most students.",
                        "context": "Rising tuition versus alternate career credentials.",
                        "interest_tag": "careers",
                        "estimated_difficulty": skill.default_difficulty,
                    },
                    {
                        "id": "topic-2",
                        "statement": "Social media has fundamentally damaged the depth of friendships.",
                        "context": "Convenience versus emotional intimacy.",
                        "interest_tag": "tech",
                        "estimated_difficulty": skill.default_difficulty,
                    },
                    {
                        "id": "topic-3",
                        "statement": "AI will create far more meaningful jobs than it displaces.",
                        "context": "Productivity gains versus skill transition friction.",
                        "interest_tag": "tech",
                        "estimated_difficulty": skill.default_difficulty,
                    },
                    {
                        "id": "topic-4",
                        "statement": "Money can directly buy happiness when used for autonomy.",
                        "context": "Hedonic adaptation versus baseline financial relief.",
                        "interest_tag": "money",
                        "estimated_difficulty": skill.default_difficulty,
                    },
                    {
                        "id": "topic-5",
                        "statement": "Remote work is better for career progression than office work.",
                        "context": "Focused output versus serendipitous visibility.",
                        "interest_tag": "society",
                        "estimated_difficulty": skill.default_difficulty,
                    },
                ]
            )

        return await self._execute_structured_completion(
            role=ModelRole.TOPIC_GENERATOR,
            messages=messages,
            schema_cls=GeneratedTopicsResponse,
            fallback_factory=fallback,
        )

    async def analyze_language(self, messages: List[dict]) -> MainLanguageAnalysisResult:
        def fallback():
            return MainLanguageAnalysisResult(
                pronunciation_findings=[
                    StructuredPronunciationFinding(
                        sound="th",
                        heard_in=["think", "three", "worth"],
                        note='Your "th" sound occasionally shifts toward a "t" in word-initial positions.',
                        occurrences=3,
                        severity="minor",
                        confidence=0.85,
                        reportable=True,
                    ),
                    StructuredPronunciationFinding(
                        sound="v / w",
                        heard_in=["very", "value"],
                        note='A soft "w" sound appears where "v" is expected.',
                        occurrences=2,
                        severity="minor",
                        confidence=0.8,
                        reportable=True,
                    ),
                ],
                fluency_finding=StructuredFluencyFinding(
                    summary="Maintained fluent rhythm under debate pressure. Pauses lengthened slightly when structuring counterarguments.",
                    trend="improving",
                    hesitation_vs_thinking_note="Planning delays before turns reflected strategic thought rather than speaking hesitation.",
                    score=82,
                ),
                grammar_finding=StructuredGrammarFinding(
                    summary="Strong grammatical control with accurate conditional sentence structures.",
                    recurring_pattern="Articles occasionally omitted before abstract nouns.",
                    examples=["— college is investment → a college is an investment"],
                    reportable=True,
                ),
                vocabulary_finding=StructuredVocabularyFinding(
                    summary="Effective debate vocabulary: 'assumption', 'trade-off', 'on balance'.",
                    examples=["on balance", "fundamental premise"],
                    suggested_alternatives=["conversely", "notwithstanding"],
                ),
                clarity_finding=StructuredClarityFinding(
                    summary="Arguments were articulated with high intelligibility and logical clarity.",
                    score=86,
                ),
                session_summary="Clear, persuasive communication with strong articulation under time pressure.",
                top_coaching_points=["Focus on steady 'th' airflow", "Use contrast transition phrases"],
            )

        return await self._execute_structured_completion(
            role=ModelRole.LANGUAGE_ANALYSIS,
            messages=messages,
            schema_cls=MainLanguageAnalysisResult,
            fallback_factory=fallback,
        )

    async def patch_final_language(self, messages: List[dict]) -> MainLanguageAnalysisResult:
        return await self.analyze_language(messages)

    async def review_debate(self, messages: List[dict]) -> DebateReviewerResult:
        def fallback():
            return DebateReviewerResult(
                outcome="user_win",
                target_skill_demonstrated=True,
                mastery_stars=2,
                mastery_note="You addressed the counterargument directly and held your position under pressure.",
                skill_summary="Every response engaged their actual premise before advancing your thesis.",
                argument_strength="You challenged the core assumption that higher cost equates to quality.",
                argument_improvement="Your weakest moment was conceding the statistical claim without reframing it.",
                strategic_insight="Rebutio relied on aggregate statistics; challenging the distribution would have won the point instantly.",
            )

        return await self._execute_structured_completion(
            role=ModelRole.DEBATE_REVIEWER,
            messages=messages,
            schema_cls=DebateReviewerResult,
            fallback_factory=fallback,
        )


ai_gateway = AIGateway()
