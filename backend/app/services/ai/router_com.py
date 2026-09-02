from typing import Any, Dict, List, Optional, Set
import httpx
from backend.app.config import settings
from backend.app.observability.logging import get_logger
from backend.app.services.ai.config import AICompletionResult

logger = get_logger("rebutio.router_com")

ROUTER_COM_BASE_URL = "https://api.router.com/v1"


class RouterComClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.RAMP_ROUTER_API_KEY
        self.base_url = ROUTER_COM_BASE_URL
        self._validated_models: Optional[Set[str]] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def get_available_models(self) -> Set[str]:
        if self._validated_models is not None:
            return self._validated_models

        if not self.is_configured:
            return set()

        try:
            url = f"{self.base_url}/models"
            headers = self._get_headers()
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    models = {m.get("id") for m in data.get("data", []) if "id" in m}
                    self._validated_models = models
                    return models
        except Exception as e:
            logger.warning("router_com.model_list_failed", error=str(e))

        return set()

    async def chat_completion_raw(
        self,
        messages: List[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        response_format_json: bool = False,
        reasoning_effort: Optional[str] = None,
    ) -> AICompletionResult:
        if not self.is_configured:
            raise ValueError("Router.com API key not configured")

        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers()

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        # Models like gpt-5.6-luna and OpenAI reasoning models reject custom temperature on Router.com (HTTP 400)
        if temperature is not None and not any(k in model.lower() for k in ["luna", "o1", "o3", "o4"]):
            payload["temperature"] = temperature

        if reasoning_effort and reasoning_effort.strip():
            payload["reasoning_effort"] = reasoning_effort.strip().lower()

        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.error("router_com.chat.error", status_code=resp.status_code)
                resp.raise_for_status()

            res_json = resp.json()
            choices = res_json.get("choices", [])
            if not choices:
                raise ValueError("Router.com returned empty choices")

            first_choice = choices[0]
            choice_msg = first_choice.get("message", {})
            raw_content = choice_msg.get("content", "") or ""
            reasoning_text = choice_msg.get("reasoning") or choice_msg.get("reasoning_content")

            import re
            extracted_thinks = re.findall(r"<think>([\s\S]*?)</think>", raw_content)
            if extracted_thinks and not reasoning_text:
                reasoning_text = "\n".join(extracted_thinks).strip()

            content = re.sub(r"<think>[\s\S]*?(?:</think>|$)", "", raw_content).strip()
            finish_reason = first_choice.get("finish_reason")

            usage = res_json.get("usage", {})
            input_tokens = usage.get("prompt_tokens")
            output_tokens = usage.get("completion_tokens")
            provider_req_id = res_json.get("id") or resp.headers.get("x-request-id")
            resolved_model = res_json.get("model") or model

            return AICompletionResult(
                content=content,
                reasoning=reasoning_text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                provider_request_id=provider_req_id,
                finish_reason=finish_reason,
                resolved_model=resolved_model,
                upstream_provider="router_com",
            )

    async def chat_completion(
        self,
        messages: List[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        response_format_json: bool = False,
        reasoning_effort: Optional[str] = None,
    ) -> str:
        res = await self.chat_completion_raw(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format_json=response_format_json,
            reasoning_effort=reasoning_effort,
        )
        return res.content


router_com_client = RouterComClient()

