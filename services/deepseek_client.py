# services/deepseek_client.py
import httpx
import os
import logging

log = logging.getLogger("deepseek")

class DeepSeekClient:
    def __init__(self, api_key: str | None):
        self.api_key = api_key
        self.base_url = "https://api.deepseek.com/v1"  # при необходимости поправим
        self._client = httpx.AsyncClient(timeout=30)

    async def chat(self, messages: list[dict], model: str = "deepseek-chat"):
        if not self.api_key:
            # В режиме без ключа просто эхо-ответ (чтобы не падать на старте)
            return {"role":"assistant", "content":"(демо) Я слышу тебя, расскажи больше."}

        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"model": model, "messages": messages}
        r = await self._client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        # приведем к удобному виду
        content = data["choices"][0]["message"]["content"]
        return {"role":"assistant", "content": content}

    async def aclose(self):
        await self._client.aclose()
