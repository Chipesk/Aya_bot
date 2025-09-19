# mypy: ignore-errors
import logging
import httpx

log = logging.getLogger("deepseek")


class DeepSeekClient:
    def __init__(self, api_key: str | None):
        self.api_key = api_key
        self.base_url = "https://api.deepseek.com/v1"
        self._client = httpx.AsyncClient(timeout=30)

    async def chat(self, messages: list[dict], model: str = "deepseek-chat"):
        if not self.api_key:
            return {"role": "assistant", "content": "(демо) Я слышу тебя, расскажи больше."}

        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"model": model, "messages": messages}
        try:
            r = await self._client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.exception("DeepSeek HTTP error: %s", e)
            raise
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        return {"role": "assistant", "content": content}

    async def health_check(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "DEEPSEEK_API_KEY not set"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            r = await self._client.get(f"{self.base_url}/models", headers=headers, timeout=10)
            if r.status_code == 200:
                return True, "auth ok"
            if r.status_code in (401, 403):
                return False, f"auth error ({r.status_code})"
            return False, f"http {r.status_code}"
        except Exception as e:
            return False, f"network error: {e}"

    async def aclose(self):
        await self._client.aclose()
