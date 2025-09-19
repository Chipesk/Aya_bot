"""Development runner that avoids talking to Telegram."""
from __future__ import annotations

from typing import Awaitable, Callable

from core.logging import get_logger

log = get_logger("dev_runner")


class DevBotRunner:
    def __init__(self, handler: Callable[[str], Awaitable[str]]):
        self.handler = handler

    async def start(self) -> None:
        log.info("dev_runner.start")
        for sample in ("Привет", "Какая погода?", "Мне 33", "У меня непереносимость лактозы"):
            response = await self.handler(sample)
            log.info("dev_runner.dialogue", user=sample, aya=response)
        log.info("dev_runner.stop")
