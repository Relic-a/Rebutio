import logging
from typing import Any, Dict, List, Optional, Set
import httpx
from backend.app.config import settings

logger = logging.getLogger("rebutio.router_com")

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
            logger.warning(f"Router.com model list fetch failed: {e}")

        return set()

    async def chat_completion(
        self,
        messages: List[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        response_format_json: bool = False,
    ) -> str:
        if not self.is_configured:
            raise ValueError("Router.com API key not configured")

        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers()

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.error(f"Router.com Chat Completion error: HTTP {resp.status_code}")
                resp.raise_for_status()

            res_json = resp.json()
            choices = res_json.get("choices", [])
            if not choices:
                raise ValueError("Router.com returned empty choices")
            content = choices[0].get("message", {}).get("content", "")
            return content.strip()


router_com_client = RouterComClient()
