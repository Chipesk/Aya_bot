"""Application entry point."""
# mypy: ignore-errors
from __future__ import annotations

import asyncio
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from adapters.telegram.dev_runner import DevBotRunner
from bot.middlewares.user_context import UserContextMiddleware
from bot.routers.basic import router as basic_router
from core.logging import get_logger, setup_logging
from core.settings import settings
from domain.memory.manager import MemoryManager
from domain.persona.service import PersonaService
from domain.policies.loader import load_policy_bundle
from domain.reasoning.decision_engine import DecisionEngine
from domain.world_state.service import WorldStateService
from memory.chat_history import ChatHistoryRepo
from memory.facts_repo import FactsRepo
from memory.repo import MemoryRepo
from orchestrator.aya_brain import AyaBrain
from services.deepseek_client import DeepSeekClient
from services.world_state import WorldState
from storage.db import DB, ensure_db_ready

log = get_logger("main")


async def app() -> None:
    setup_logging(settings.LOG_LEVEL, json_mode=settings.is_prod, diag=settings.is_diag)
    db = await ensure_db_ready(DB(settings.DB_PATH))

    memory_repo = MemoryRepo(db)
    chat_history = ChatHistoryRepo(db)
    facts_repo = FactsRepo(db)
    deepseek = DeepSeekClient(settings.DEEPSEEK_API_KEY or None)
    world_backend = WorldState(db=db, fetcher=_dummy_weather_fetch, ttl_sec=900)
    world_service = WorldStateService(world_backend)
    persona_service = PersonaService()
    memory_manager = MemoryManager(memory_repo, facts_repo, chat_history)

    policy_bundle = load_policy_bundle(Path("policies"))
    decision_engine = DecisionEngine(policy_bundle)

    aya_brain = AyaBrain(
        deepseek,
        memory_repo,
        memory_manager,
        world_service,
        persona_service,
        decision_engine,
        facts_repo,
    )

    token = settings.bot_token()
    if token == "TEST:TOKEN" and settings.ENV in {"dev", "test"}:
        log.info("Starting dev runner")

        async def dev_handle(text: str) -> str:
            response = await aya_brain.respond(0, text)
            return response.text

        runner = DevBotRunner(dev_handle)
        await runner.start()
    else:
        bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = Dispatcher()
        dp.update.middleware(UserContextMiddleware(memory_repo))
        dp["aya_brain"] = aya_brain
        dp["memory_repo"] = memory_repo
        dp["world_state"] = world_service
        dp["chat_history"] = chat_history
        dp["facts_repo"] = facts_repo
        dp.include_router(basic_router)
        log.info("Start polling")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

    await deepseek.aclose()
    await db.close()


async def _dummy_weather_fetch() -> dict:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo(settings.AYA_TZ))
    return {
        "city": settings.AYA_CITY,
        "local_time_iso": now.isoformat(timespec="seconds"),
        "weather": {"temp_c": 10, "is_rainy": False},
    }


if __name__ == "__main__":
    asyncio.run(app())
