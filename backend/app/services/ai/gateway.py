import json
import re
import time
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
from backend.app.observability.diagnostics import (
    detect_prompt_leak,
    extract_message_structure,
    format_sensitive_debug,
)
from backend.app.observability.logging import get_logger
from backend.app.observability.prompts import get_prompt_version
from backend.app.services.ai.config import (
    AICompletionResult,
    ModelRole,
    ProviderType,
    RoleCandidate,
    get_role_candidates,
)
from backend.app.services.ai.openrouter import openrouter_client
from backend.app.services.ai.router_com import router_com_client

logger = get_logger("rebutio.ai_gateway")

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
        Logs safe metrics: audio duration/size, response timings, word counts.
        Never logs audio or transcripts in production.
        """
        if not audio_bytes:
            return ""

        audio_size_bytes = len(audio_bytes)
        audio_dur_ms = max(0, min(30000, audio_size_bytes // 32))

        logger.info(
            "speech.transcription.started",
            audio_size_bytes=audio_size_bytes,
            audio_duration_ms=audio_dur_ms,
            audio_format=audio_format,
            provider="openrouter",
            model=settings.OPENROUTER_TRANSCRIPTION_MODEL,
        )

        candidates = get_role_candidates(ModelRole.TRANSCRIPTION)
        last_error = None
        start_time = time.perf_counter()

        for cand in candidates:
            if cand.provider == ProviderType.OPENROUTER and self.openrouter.is_configured:
                for attempt in range(2):
                    if attempt > 0:
                        logger.warning(
                            "provider.retry",
                            role=ModelRole.TRANSCRIPTION.value,
                            provider="openrouter",
                            model=cand.model_id,
                            attempt=attempt + 1,
                            max_attempts=2,
                            reason=str(last_error) if last_error else "transient_error",
                        )
                    try:
                        t_start = time.perf_counter()
                        text = await self.openrouter.transcribe_audio(
                            audio_bytes=audio_bytes,
                            audio_format=audio_format,
                            model=cand.model_id,
                        )
                        dur_ms = round((time.perf_counter() - t_start) * 1000, 2)
                        if text is not None:
                            cleaned_text = text.strip()
                            if cleaned_text:
                                char_count = len(cleaned_text)
                                word_count = len(cleaned_text.split())
                                logger.info(
                                    "speech.transcription.completed",
                                    duration_ms=dur_ms,
                                    audio_size_bytes=audio_size_bytes,
                                    transcript_char_count=char_count,
                                    transcript_word_count=word_count,
                                )
                                if settings.LOG_AI_CONTENT:
                                    logger.debug("speech.transcription.content", debug_snippet=format_sensitive_debug(cleaned_text))
                                return cleaned_text
                            else:
                                logger.info(
                                    "speech.transcription.empty",
                                    duration_ms=dur_ms,
                                    audio_size_bytes=audio_size_bytes,
                                    reason="no_speech_detected_in_audio",
                                )
                                return ""
                    except Exception as e:
                        last_error = e

        dur_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error(
            "speech.transcription.failed",
            duration_ms=dur_ms,
            audio_size_bytes=audio_size_bytes,
            exception_type=last_error.__class__.__name__ if last_error else "ProviderUnavailable",
        )
        error_msg = f"Audio transcription failed: {last_error or 'STT provider unavailable'}"
        raise RuntimeError(error_msg)

    async def synthesize_speech(self, text: str, voice: Optional[str] = None) -> bytes:
        """
        Synthesizes opponent speech using Fish Audio S2.1 Pro / configured TTS model.
        """
        if not text:
            return b""

        text_chars = len(text)
        voice_name = voice if voice is not None else settings.REBUTIO_TTS_VOICE

        logger.info(
            "debate.tts.started",
            text_char_count=text_chars,
            voice=voice_name,
            provider="openrouter",
            model=settings.OPENROUTER_TTS_MODEL,
        )

        candidates = get_role_candidates(ModelRole.SPEECH)
        start_time = time.perf_counter()

        for cand in candidates:
            if cand.provider == ProviderType.OPENROUTER and self.openrouter.is_configured:
                try:
                    audio_bytes = await self.openrouter.synthesize_speech(
                        text=text,
                        voice=voice_name,
                        model=cand.model_id,
                    )
                    dur_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    if audio_bytes and len(audio_bytes) > 0:
                        logger.info(
                            "debate.tts.completed",
                            duration_ms=dur_ms,
                            audio_size_bytes=len(audio_bytes),
                            text_char_count=text_chars,
                        )
                        return audio_bytes
                except Exception as e:
                    logger.warning(
                        "debate.tts.failed_candidate",
                        provider=cand.provider.value,
                        model=cand.model_id,
                        exception_type=e.__class__.__name__,
                    )

        dur_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.warning("debate.tts.failed", duration_ms=dur_ms, reason="all_candidates_failed")
        return b""

    async def generate_debate_response(self, messages: List[dict], current_turn: int = 1) -> str:
        """
        Generates Rebutio's next spoken debate argument using DeepSeek V4 Pro.
        Output is checked for prompt/instruction leakage before delivery.
        """
        role = ModelRole.DEBATE_OPPONENT
        template_name = "debate_opponent"
        prompt_version = get_prompt_version(template_name)
        struct_meta = extract_message_structure(messages, structured_output=False)

        candidates = get_role_candidates(role)
        prev_cand: Optional[RoleCandidate] = None

        for cand_idx, cand in enumerate(candidates):
            if prev_cand is not None:
                logger.warning(
                    "ai.provider_fallback",
                    role=role.value,
                    from_provider=prev_cand.provider.value,
                    from_model=prev_cand.model_id,
                    to_provider=cand.provider.value,
                    to_model=cand.model_id,
                    reason="candidate_failure_or_unconfigured",
                )
            prev_cand = cand

            logger.info(
                "ai.request.started",
                role=role.value,
                provider=cand.provider.value,
                model=cand.model_id,
                prompt_template=template_name,
                prompt_version=prompt_version,
                message_count=struct_meta.message_count,
                system_message_count=struct_meta.system_message_count,
                user_message_count=struct_meta.user_message_count,
                assistant_message_count=struct_meta.assistant_message_count,
                input_character_count=struct_meta.input_character_count,
                message_roles=struct_meta.message_roles,
                message_structures=struct_meta.message_structures,
                structured_output=False,
            )

            if settings.LOG_AI_CONTENT:
                # Bounded debug logging only in local dev when explicitly enabled
                for m in messages:
                    logger.debug(
                        "ai.request.content_debug",
                        role=m.get("role"),
                        snippet=format_sensitive_debug(m.get("content", "")),
                    )

            start_time = time.perf_counter()
            try:
                raw_res: Optional[AICompletionResult] = None
                if cand.provider == ProviderType.ROUTER_COM and self.router_com.is_configured:
                    raw_res = await self.router_com.chat_completion_raw(
                        messages=messages,
                        model=cand.model_id,
                        temperature=cand.temperature,
                        max_tokens=cand.max_tokens,
                    )
                elif cand.provider == ProviderType.OPENROUTER and self.openrouter.is_configured:
                    raw_res = await self.openrouter.chat_completion_raw(
                        messages=messages,
                        model=cand.model_id,
                        temperature=cand.temperature,
                        max_tokens=cand.max_tokens,
                    )

                if raw_res and raw_res.content:
                    dur_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    cleaned_text = self._clean_opponent_text(raw_res.content)
                    char_count = len(cleaned_text)
                    word_count = len(cleaned_text.split())

                    logger.info(
                        "ai.request.completed",
                        role=role.value,
                        provider=cand.provider.value,
                        model=cand.model_id,
                        resolved_model=raw_res.resolved_model,
                        upstream_provider=raw_res.upstream_provider,
                        duration_ms=dur_ms,
                        input_tokens=raw_res.input_tokens,
                        output_tokens=raw_res.output_tokens,
                        provider_request_id=raw_res.provider_request_id,
                        finish_reason=raw_res.finish_reason,
                        fallback_used=(cand_idx > 0),
                        retry_count=0,
                        response_char_count=char_count,
                        response_word_count=word_count,
                    )

                    if settings.LOG_AI_CONTENT:
                        logger.debug("ai.response.content_debug", snippet=format_sensitive_debug(cleaned_text))

                    # Run Prompt-leak diagnostic guardrail
                    leak_report = detect_prompt_leak(cleaned_text)
                    if leak_report.is_leak_suspected:
                        logger.warning(
                            "ai.prompt_leak_suspected",
                            role=role.value,
                            provider=cand.provider.value,
                            model=cand.model_id,
                            prompt_version=prompt_version,
                            response_hash=leak_report.response_hash,
                            response_char_count=leak_report.response_char_count,
                            matched_patterns=leak_report.matched_patterns,
                            confidence=leak_report.confidence,
                        )
                        if leak_report.confidence == "high":
                            logger.error(
                                "debate.opponent_generation.failed",
                                reason="prompt_leak_guard_triggered",
                                action="triggering_controlled_fallback",
                            )
                            # Do NOT leak instruction text to user; trigger next fallback
                            continue

                    return cleaned_text

            except Exception as e:
                dur_ms = round((time.perf_counter() - start_time) * 1000, 2)
                logger.warning(
                    "ai.request.failed",
                    role=role.value,
                    provider=cand.provider.value,
                    model=cand.model_id,
                    duration_ms=dur_ms,
                    exception_type=e.__class__.__name__,
                )

        # Fallback response for offline / test mode or all candidate failure
        logger.info(
            "ai.provider_fallback",
            role=role.value,
            from_provider=prev_cand.provider.value if prev_cand else "unknown",
            from_model=prev_cand.model_id if prev_cand else "unknown",
            to_provider="static_fallback",
            to_model="curated_responses",
            reason="all_ai_candidates_exhausted",
        )
        mock_responses = [
            "Your argument rests on an unproven assumption, but it overlooks the core mechanism. If what you claim were true, we would see far different real-world outcomes.",
            "You say this is about individual freedom, but you haven't shown why the negative externalities should be ignored. Where does your principle draw the boundary?",
            "That is a common defense, yet the evidence points in the opposite direction. What is the single strongest reason that withstands this counterexample?",
        ]
        return mock_responses[(current_turn - 1) % len(mock_responses)]

    def _clean_opponent_text(self, text: str) -> str:
        cleaned = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
        cleaned = re.sub(r"^\s*[-*•]\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"^(?:Rebutio(?:\s+responds)?|Opponent|Assistant|AI)\s*:\s*", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
        cleaned = re.sub(r"^Rebutio\s+responds\s*", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
        cleaned = cleaned.replace("**", "").replace('"', "")
        return cleaned.strip()

    async def _execute_structured_completion(
        self,
        role: ModelRole,
        messages: List[dict],
        schema_cls: Type[T],
        fallback_factory: Any,
    ) -> T:
        template_name = role.value
        prompt_version = get_prompt_version(template_name)
        struct_meta = extract_message_structure(messages, structured_output=True)

        candidates = get_role_candidates(role)
        prev_cand: Optional[RoleCandidate] = None

        for cand_idx, cand in enumerate(candidates):
            if prev_cand is not None:
                logger.warning(
                    "ai.provider_fallback",
                    role=role.value,
                    from_provider=prev_cand.provider.value,
                    from_model=prev_cand.model_id,
                    to_provider=cand.provider.value,
                    to_model=cand.model_id,
                    reason="candidate_failure_or_unconfigured",
                )
            prev_cand = cand

            logger.info(
                "ai.request.started",
                role=role.value,
                provider=cand.provider.value,
                model=cand.model_id,
                prompt_template=template_name,
                prompt_version=prompt_version,
                message_count=struct_meta.message_count,
                system_message_count=struct_meta.system_message_count,
                user_message_count=struct_meta.user_message_count,
                assistant_message_count=struct_meta.assistant_message_count,
                input_character_count=struct_meta.input_character_count,
                message_roles=struct_meta.message_roles,
                message_structures=struct_meta.message_structures,
                structured_output=True,
            )

            if settings.LOG_AI_CONTENT:
                for m in messages:
                    logger.debug(
                        "ai.request.content_debug",
                        role=m.get("role"),
                        snippet=format_sensitive_debug(m.get("content", "")),
                    )

            start_time = time.perf_counter()
            try:
                raw_res: Optional[AICompletionResult] = None
                if cand.provider == ProviderType.ROUTER_COM and self.router_com.is_configured:
                    raw_res = await self.router_com.chat_completion_raw(
                        messages=messages,
                        model=cand.model_id,
                        temperature=cand.temperature,
                        max_tokens=cand.max_tokens,
                        response_format_json=True,
                    )
                elif cand.provider == ProviderType.OPENROUTER and self.openrouter.is_configured:
                    raw_res = await self.openrouter.chat_completion_raw(
                        messages=messages,
                        model=cand.model_id,
                        temperature=cand.temperature,
                        max_tokens=cand.max_tokens,
                        response_format_json=True,
                    )

                if raw_res and raw_res.content:
                    dur_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    raw_text = raw_res.content
                    try:
                        cleaned = clean_json_string(raw_text)
                        parsed_json = json.loads(cleaned)
                        validated_obj = schema_cls.model_validate(parsed_json)

                        logger.info(
                            "ai.request.completed",
                            role=role.value,
                            provider=cand.provider.value,
                            model=cand.model_id,
                            resolved_model=raw_res.resolved_model,
                            upstream_provider=raw_res.upstream_provider,
                            duration_ms=dur_ms,
                            input_tokens=raw_res.input_tokens,
                            output_tokens=raw_res.output_tokens,
                            provider_request_id=raw_res.provider_request_id,
                            finish_reason=raw_res.finish_reason,
                            structured_validation_success=True,
                            fallback_used=(cand_idx > 0),
                            retry_count=0,
                        )
                        return validated_obj

                    except Exception as parse_err:
                        logger.warning(
                            "ai.structured_validation_failed",
                            role=role.value,
                            provider=cand.provider.value,
                            model=cand.model_id,
                            duration_ms=dur_ms,
                            parse_error=str(parse_err),
                            attempting_repair=True,
                        )
                        # 1 constrained repair retry
                        repair_prompt = [
                            {"role": "system", "content": "You are a JSON repair tool. Output only the valid JSON object conforming to the required schema, with no markdown or explanation."},
                            {"role": "user", "content": f"Fix this invalid JSON to match the expected format:\n{raw_text}"}
                        ]
                        logger.info(
                            "provider.retry",
                            role=role.value,
                            provider="openrouter",
                            attempt=2,
                            max_attempts=2,
                            reason="schema_repair_retry",
                        )
                        if cand.provider == ProviderType.OPENROUTER and self.openrouter.is_configured:
                            rep_res = await self.openrouter.chat_completion_raw(
                                messages=repair_prompt,
                                model=cand.model_id,
                                temperature=0.0,
                                max_tokens=cand.max_tokens,
                                response_format_json=True,
                            )
                            cleaned_rep = clean_json_string(rep_res.content)
                            validated_obj = schema_cls.model_validate(json.loads(cleaned_rep))
                            logger.info(
                                "ai.request.completed",
                                role=role.value,
                                provider=cand.provider.value,
                                model=cand.model_id,
                                structured_validation_success=True,
                                repaired=True,
                            )
                            return validated_obj

            except Exception as e:
                dur_ms = round((time.perf_counter() - start_time) * 1000, 2)
                logger.warning(
                    "ai.request.failed",
                    role=role.value,
                    provider=cand.provider.value,
                    model=cand.model_id,
                    duration_ms=dur_ms,
                    exception_type=e.__class__.__name__,
                )

        logger.info(
            "ai.provider_fallback",
            role=role.value,
            from_provider=prev_cand.provider.value if prev_cand else "unknown",
            from_model=prev_cand.model_id if prev_cand else "unknown",
            to_provider="static_fallback",
            to_model="default_schema_factory",
            reason="all_ai_candidates_exhausted",
        )
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
                pronunciation_findings=[],
                fluency_finding=StructuredFluencyFinding(
                    summary="Speech flow was maintained across the debate exchanges.",
                    trend="steady",
                    hesitation_vs_thinking_note="Planning time prior to turns reflected argument formulation.",
                    score=75,
                ),
                grammar_finding=StructuredGrammarFinding(
                    summary="Communicated argument clearly with understandable sentence structures.",
                    recurring_pattern=None,
                    examples=[],
                    reportable=False,
                ),
                vocabulary_finding=StructuredVocabularyFinding(
                    summary="Used appropriate vocabulary to defend the position.",
                    examples=[],
                    suggested_alternatives=[],
                ),
                clarity_finding=StructuredClarityFinding(
                    summary="Points were articulated intelligibly throughout the turns.",
                    score=80,
                ),
                session_summary="Completed debate session with clear articulation and responsive reasoning.",
                top_coaching_points=["Continue challenging opposing premises directly."],
            )

        return await self._execute_structured_completion(
            role=ModelRole.LANGUAGE_ANALYSIS,
            messages=messages,
            schema_cls=MainLanguageAnalysisResult,
            fallback_factory=fallback,
        )

    async def patch_final_language(self, messages: List[dict]) -> MainLanguageAnalysisResult:
        def fallback():
            return MainLanguageAnalysisResult(
                pronunciation_findings=[],
                fluency_finding=StructuredFluencyFinding(
                    summary="Speech flow was maintained across the debate exchanges.",
                    trend="steady",
                    hesitation_vs_thinking_note="Planning time prior to turns reflected argument formulation.",
                    score=75,
                ),
                grammar_finding=StructuredGrammarFinding(
                    summary="Communicated argument clearly with understandable sentence structures.",
                    recurring_pattern=None,
                    examples=[],
                    reportable=False,
                ),
                vocabulary_finding=StructuredVocabularyFinding(
                    summary="Used appropriate vocabulary to defend the position.",
                    examples=[],
                    suggested_alternatives=[],
                ),
                clarity_finding=StructuredClarityFinding(
                    summary="Points were articulated intelligibly throughout the turns.",
                    score=80,
                ),
                session_summary="Completed debate session with clear articulation and responsive reasoning.",
                top_coaching_points=["Continue challenging opposing premises directly."],
            )

        return await self._execute_structured_completion(
            role=ModelRole.FINAL_LANGUAGE_PATCH,
            messages=messages,
            schema_cls=MainLanguageAnalysisResult,
            fallback_factory=fallback,
        )

    async def review_debate(self, messages: List[dict]) -> DebateReviewerResult:
        def fallback():
            return DebateReviewerResult(
                outcome="undetermined",
                target_skill_demonstrated=False,
                mastery_stars=1,
                mastery_note="Completed the debate turns.",
                skill_summary="Completed all turns under the target skill focus.",
                argument_strength="You articulated your position clearly across all turns.",
                argument_improvement="Continue pressing on core opposing assumptions in future debates.",
                strategic_insight=None,
            )

        return await self._execute_structured_completion(
            role=ModelRole.DEBATE_REVIEWER,
            messages=messages,
            schema_cls=DebateReviewerResult,
            fallback_factory=fallback,
        )


ai_gateway = AIGateway()
