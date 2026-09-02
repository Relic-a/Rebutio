from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from backend.app.domain.evidence import assess_debate_evidence
from backend.app.prompts.debate_reviewer import build_debate_reviewer_prompt
from backend.app.prompts.language_analysis import build_language_analysis_prompt
from workbench.state.models import (
    DebateState,
    EvidenceAssessmentData,
    ReviewState,
    ScoreCard,
)


class ReviewerEngine:
    """
    Isolated engine for debate scoring, rubrics, stars, and language analysis.
    Takes a DebateState and evaluates it without requiring live debates or DB sessions.
    """

    @classmethod
    async def run_review(
        cls,
        debate_state: DebateState,
        live: bool = False,
    ) -> ReviewState:
        t_start = time.perf_counter()
        full_transcript = debate_state.to_transcript_dicts()
        all_evidence = debate_state.evidence or []

        # 1. Evidence Assessment
        ev_assessment = assess_debate_evidence(full_transcript, all_evidence)
        ev_data = EvidenceAssessmentData(
            has_sufficient_evidence=ev_assessment.has_sufficient_evidence,
            has_sufficient_delivery_evidence=ev_assessment.has_sufficient_delivery_evidence,
            user_turns_count=ev_assessment.user_turns_count,
            substantive_turns_count=ev_assessment.substantive_turns_count,
            total_user_words=ev_assessment.total_user_words,
            insufficient_reason=ev_assessment.insufficient_reason,
        )

        session_id = debate_state.session_id
        topic = debate_state.topic
        user_side = debate_state.user_side
        opp_side = debate_state.opponent_side
        skill_id = debate_state.skill_id
        skill_name = debate_state.skill_name
        difficulty = debate_state.difficulty

        # 2. Insufficient Evidence Branch
        if not ev_assessment.has_sufficient_evidence:
            dur_ms = round((time.perf_counter() - t_start) * 1000, 2)
            return ReviewState(
                session_id=session_id,
                topic=topic,
                user_side=user_side,
                opponent_side=opp_side,
                skill_id=skill_id,
                skill_name=skill_name,
                difficulty=difficulty,
                evidence_assessment=ev_data,
                outcome="undetermined",
                mastery_stars=0,
                completed=False,
                skill_demonstrated=False,
                mastery_note="Session concluded before substantive debate arguments were established.",
                skill_summary="Session ended before target skill could be demonstrated.",
                score_technique=ScoreCard(
                    score=None,
                    label="Debate technique",
                    rubric="Insufficient debate exchanges to evaluate technique.",
                ),
                score_grammar=ScoreCard(
                    score=None,
                    label="Grammar",
                    rubric="Insufficient speech data to evaluate grammar.",
                ),
                score_vocabulary=ScoreCard(
                    score=None,
                    label="Vocabulary",
                    rubric="Insufficient vocabulary sample from this session.",
                ),
                score_delivery=ScoreCard(
                    score=None,
                    label="Delivery",
                    rubric="Insufficient audio recording length to evaluate delivery.",
                ),
                strongest_moment=None,
                improvement_opportunity="Engage in at least two full debate turns with reasons and examples to receive targeted coaching.",
                argument_feedback={
                    "strength": "Session concluded before substantive debate arguments were established.",
                    "improvement": "Engage in full debate exchanges to receive strategic feedback.",
                    "insight": None,
                },
                language_feedback=None,
                duration_ms=dur_ms,
            )

        turns_evidence = []
        for t in debate_state.turns:
            if t.speaker == "user":
                matching_ev = next((e for e in all_evidence if e.get("turn_number") == t.turn_number), {})
                turns_evidence.append({
                    "turn_number": t.turn_number,
                    "transcript": t.text,
                    "translation": getattr(t, "translation", None) or matching_ev.get("translation"),
                    "phonemes": matching_ev.get("phonemes", []) or (t.audio_metrics or {}).get("phonemes", []),
                    "phoneme_evidence": matching_ev.get("phonemes", []) or (t.audio_metrics or {}).get("phonemes", []),
                    "client_response_delay_ms": (t.audio_metrics or {}).get("client_response_delay_ms", 0),
                    "speech_metrics": matching_ev.get("speech_metrics", {}),
                })

        # 3. Build Prompts
        reviewer_messages = build_debate_reviewer_prompt(
            topic=topic,
            user_side=user_side,
            opponent_side=opp_side,
            skill_id=skill_id,
            skill_name=skill_name,
            difficulty=difficulty,
            full_transcript=full_transcript,
            turns_evidence=turns_evidence,
        )

        language_messages = build_language_analysis_prompt(
            topic=topic,
            target_skill=skill_name,
            difficulty=difficulty,
            turns_evidence=turns_evidence,
        )

        raw_reviewer_dict = None
        raw_language_dict = None

        if live:
            from backend.app.services.ai.gateway import ai_gateway
            rev_task = asyncio.create_task(ai_gateway.review_debate(reviewer_messages))
            lang_task = asyncio.create_task(ai_gateway.analyze_language(language_messages))
            results = await asyncio.gather(rev_task, lang_task, return_exceptions=True)

            reviewer_res = results[0] if not isinstance(results[0], Exception) else None
            lang_res = results[1] if not isinstance(results[1], Exception) else None

            if reviewer_res:
                raw_reviewer_dict = reviewer_res.model_dump()
                outcome = reviewer_res.outcome if reviewer_res.outcome in ("user_win", "opponent_win", "draw", "undetermined") else "undetermined"
                mastery_stars = max(1, min(3, reviewer_res.mastery_stars or 1))
                skill_demo = reviewer_res.target_skill_demonstrated
                mastery_note = reviewer_res.mastery_note
                skill_summary = reviewer_res.skill_summary
                score_tech = reviewer_res.score_technique
                rubric_tech = reviewer_res.score_technique_rubric or "Directly addressed opposing claims with clear argumentative logic."
                score_gram = reviewer_res.score_grammar
                rubric_gram = reviewer_res.score_grammar_rubric or "Clean sentence structures with minimal syntactic friction."
                score_vocab = reviewer_res.score_vocabulary
                rubric_vocab = reviewer_res.score_vocabulary_rubric or "Appropriate and precise word choices tailored to the topic."

                if ev_assessment.has_sufficient_delivery_evidence:
                    score_deliv = reviewer_res.score_delivery
                    rubric_deliv = reviewer_res.score_delivery_rubric or "Consistent pacing with natural pauses between points."
                else:
                    score_deliv = None
                    rubric_deliv = "No audio recording available to evaluate spoken delivery."

                strongest_moment = reviewer_res.strongest_moment
                improvement_opp = reviewer_res.improvement_opportunity
                grammar_advice = reviewer_res.grammar_advice
                vocabulary_advice = reviewer_res.vocabulary_advice
                pronunciation_advice = reviewer_res.pronunciation_advice
                arg_feedback = {
                    "strength": reviewer_res.argument_strength or "Articulated your position across the exchange.",
                    "improvement": reviewer_res.argument_improvement or "Push more aggressively on the core opposing premise.",
                    "insight": reviewer_res.strategic_insight,
                }
            else:
                outcome = "undetermined"
                mastery_stars = 1
                skill_demo = False
                mastery_note = "Review service encountered an issue; fallback scoring applied."
                skill_summary = f"Addressed the topic with focus on {skill_name}."
                score_tech, rubric_tech = None, "Evaluation unavailable."
                score_gram, rubric_gram = None, "Evaluation unavailable."
                score_vocab, rubric_vocab = None, "Evaluation unavailable."
                score_deliv, rubric_deliv = None, "Evaluation unavailable."
                strongest_moment = None
                improvement_opp = "Review service unavailable."
                grammar_advice = None
                vocabulary_advice = None
                pronunciation_advice = None
                arg_feedback = {"strength": "Completed the debate exchange.", "improvement": "Try another round.", "insight": None}

            lang_feedback = None
            if lang_res:
                raw_language_dict = lang_res.model_dump()
                pron_list = [
                    {
                        "sound": p.sound,
                        "heard_in": p.heard_in,
                        "note": p.note,
                        "occurrences": p.occurrences,
                        "severity": p.severity,
                        "confidence": p.confidence,
                        "reportable": p.reportable,
                    }
                    for p in lang_res.pronunciation_findings
                    if p.reportable
                ]
                lang_feedback = {
                    "pronunciation": pron_list,
                    "fluency": lang_res.fluency_finding.model_dump() if lang_res.fluency_finding else None,
                    "grammar": lang_res.grammar_finding.model_dump() if lang_res.grammar_finding else None,
                    "vocabulary": lang_res.vocabulary_finding.model_dump() if lang_res.vocabulary_finding else None,
                    "clarity": lang_res.clarity_finding.model_dump() if lang_res.clarity_finding else None,
                }
        else:
            # Deterministic mock scoring based on user turns and evidence
            user_turns = debate_state.user_turns
            user_word_count = sum(len(t.text.split()) for t in user_turns)
            stars = 3 if user_word_count > 90 and len(user_turns) >= 3 else 2
            outcome = "user_win" if stars == 3 else "draw"

            score_tech = 9 if stars == 3 else 8
            rubric_tech = "Targeted the economic assumption in turn 2 and synthesized the apprenticeship problem in the closing turn." if stars == 3 else "Clear refutation of the primary opposing premise."

            score_gram = 9 if stars == 3 else 8
            rubric_gram = "Complex conditional structures delivered with syntactic precision under pressure."

            score_vocab = 8
            rubric_vocab = "Effective domain terminology including 'apprenticeship gap', 'proportionally', and 'review bottlenecks'."

            score_deliv = 8 if ev_assessment.has_sufficient_delivery_evidence else None
            rubric_deliv = "Measured cadence averaging 138 WPM with clean transitions between points." if ev_assessment.has_sufficient_delivery_evidence else "No audio recording available to evaluate delivery."

            strongest_moment = "Turn 2: Crisp spoken delivery of complex conditional syntax without hesitation."
            improvement_opp = "Vary spoken sentence lengths so key points stand out with more rhythmic punch."
            grammar_advice = "Solid use of concessive clauses ('While AI writes...', 'Even with fixed budgets...'); watch clause density to avoid overly long spoken run-ons."
            vocabulary_advice = "Effective domain terminology including 'apprenticeship gap' and 'constrained budgets'; try 'diminish' or 'curtail' as alternatives to 'cut'."
            pronunciation_advice = "In Turn 2, the voiceless dental fricative /θ/ in [[pronounce:proportionally]] softened toward /s/. Place the tongue tip lightly between your front teeth."

            arg_feedback = {
                "strength": "Refusing to allow the opponent to pivot from budget constraints to theoretical software demand.",
                "improvement": "Offer a brief quantitative example of review bottlenecks to lock the final argument down.",
                "insight": "The debate turned decisively on who could realistically explain how juniors become seniors.",
            }

            lang_feedback = {
                "pronunciation": [
                    {
                        "sound": "θ",
                        "heard_in": ["proportionally", "therefore"],
                        "note": "Voiceless dental fricative slightly softened towards /s/.",
                        "occurrences": 2,
                        "severity": "minor",
                        "confidence": 0.88,
                        "reportable": True,
                    }
                ],
                "fluency": {
                    "summary": "Confident pacing across exchanges with negligible hesitation.",
                    "trend": "improving",
                    "score": 88,
                },
                "grammar": {
                    "summary": "Clean sentence construction across turns.",
                    "recurring_pattern": None,
                },
                "vocabulary": {
                    "examples": ["apprenticeship gap", "constrained budgets"],
                    "recommendations": [],
                },
                "clarity": {
                    "summary": "Crisp logic chain easily followed by the adjudicator.",
                    "score": 92,
                },
            }

            mastery_stars = stars
            skill_demo = True
            mastery_note = "Consistently dismantled the opponent's core premises regarding budget growth and mentorship pipelines."
            skill_summary = f"Exemplary demonstration of {skill_name} across all turns."
            raw_reviewer_dict = {"mock": True, "stars": stars, "outcome": outcome}
            raw_language_dict = {"mock": True, "feedback": lang_feedback}

        dur_ms = round((time.perf_counter() - t_start) * 1000, 2)

        return ReviewState(
            session_id=session_id,
            topic=topic,
            user_side=user_side,
            opponent_side=opp_side,
            skill_id=skill_id,
            skill_name=skill_name,
            difficulty=difficulty,
            evidence_assessment=ev_data,
            outcome=outcome,
            mastery_stars=mastery_stars,
            completed=True,
            skill_demonstrated=skill_demo,
            mastery_note=mastery_note,
            skill_summary=skill_summary,
            score_technique=ScoreCard(score=score_tech, label="Debate technique", rubric=rubric_tech),
            score_grammar=ScoreCard(score=score_gram, label="Grammar", rubric=rubric_gram),
            score_vocabulary=ScoreCard(score=score_vocab, label="Vocabulary", rubric=rubric_vocab),
            score_delivery=ScoreCard(score=score_deliv, label="Delivery", rubric=rubric_deliv),
            strongest_moment=strongest_moment,
            improvement_opportunity=improvement_opp,
            grammar_advice=grammar_advice,
            vocabulary_advice=vocabulary_advice,
            pronunciation_advice=pronunciation_advice,
            argument_feedback=arg_feedback,
            language_feedback=lang_feedback,
            raw_reviewer_response=raw_reviewer_dict,
            raw_language_response=raw_language_dict,
            prompt_messages_reviewer=reviewer_messages,
            prompt_messages_language=language_messages,
            duration_ms=dur_ms,
        )
