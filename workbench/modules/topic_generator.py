from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

from backend.app.prompts.topic_generator import build_topic_generator_prompt
from workbench.state.models import GeneratedTopic, TopicGeneratorInput, TopicGeneratorState


class TopicGeneratorEngine:
    """
    Isolated engine for generating debate motions, testing topic prompts,
    and exposing prompts & raw AI responses for iterative development.
    """

    @classmethod
    async def run(
        cls,
        state: Optional[TopicGeneratorState] = None,
        live: bool = False,
    ) -> TopicGeneratorState:
        if state is None:
            state = TopicGeneratorState()

        inputs = state.inputs
        t_start = time.perf_counter()

        prompt_messages = build_topic_generator_prompt(
            skill_id=inputs.skill_id,
            skill_name=inputs.skill_name,
            difficulty=inputs.difficulty,
            user_interests=inputs.user_interests,
            recent_topics=inputs.recent_topics,
            compact_speech_findings=inputs.compact_speech_findings,
            count=inputs.count,
        )

        generated_topics: List[GeneratedTopic] = []
        raw_response: Optional[str] = None

        if live:
            from backend.app.services.ai.gateway import ai_gateway
            topics_resp = await ai_gateway.generate_topics(
                messages=prompt_messages,
                skill_id=inputs.skill_id,
            )
            if hasattr(topics_resp, "model_dump_json"):
                raw_response = topics_resp.model_dump_json(indent=2)
            else:
                raw_response = json.dumps(topics_resp, indent=2)

            topics_list = getattr(topics_resp, "topics", [])
            for item in topics_list:
                item_dict = item.model_dump() if hasattr(item, "model_dump") else (item if isinstance(item, dict) else {})
                generated_topics.append(
                    GeneratedTopic(
                        id=item_dict.get("id", f"topic-{uuid.uuid4().hex[:6]}"),
                        statement=item_dict.get("statement", ""),
                        context=item_dict.get("context"),
                        interest_tag=item_dict.get("interest_tag"),
                        estimated_difficulty=item_dict.get("estimated_difficulty") or inputs.difficulty,
                        skill_id=inputs.skill_id,
                        turns=3,
                        minutes=4,
                        reminder=f"Focus on practicing {inputs.skill_name}.",
                    )
                )
        else:
            # Deterministic mock response for instant offline iteration & testing
            raw_mock_payload = {
                "topics": [
                    {
                        "id": f"topic-{inputs.skill_id}-1",
                        "statement": "AI generated code will eliminate junior software developer roles within three years.",
                        "context": "Balancing automated code generation efficiency against foundational engineering apprenticeship.",
                        "interest_tag": "technology",
                        "estimated_difficulty": inputs.difficulty,
                    },
                    {
                        "id": f"topic-{inputs.skill_id}-2",
                        "statement": "Companies should prohibit employees from using proprietary data in public LLM prompts.",
                        "context": "Balancing organizational data privacy safeguards with individual productivity gains.",
                        "interest_tag": "ethics",
                        "estimated_difficulty": inputs.difficulty,
                    },
                    {
                        "id": f"topic-{inputs.skill_id}-3",
                        "statement": "Remote workers should receive lower salaries than in-office workers in high-cost cities.",
                        "context": "Weighing geographic living expenses against equal pay for equal value of output.",
                        "interest_tag": "careers",
                        "estimated_difficulty": inputs.difficulty,
                    },
                ][: inputs.count]
            }
            raw_response = json.dumps(raw_mock_payload, indent=2)
            for t in raw_mock_payload["topics"]:
                generated_topics.append(
                    GeneratedTopic(
                        id=t["id"],
                        statement=t["statement"],
                        context=t["context"],
                        interest_tag=t["interest_tag"],
                        estimated_difficulty=t["estimated_difficulty"],
                        skill_id=inputs.skill_id,
                        turns=3,
                        minutes=4,
                        reminder=f"Focus on practicing {inputs.skill_name}.",
                    )
                )

        dur_ms = round((time.perf_counter() - t_start) * 1000, 2)

        return TopicGeneratorState(
            inputs=inputs,
            generated_topics=generated_topics,
            prompt_messages=prompt_messages,
            raw_response=raw_response,
            duration_ms=dur_ms,
        )
