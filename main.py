# main.py
import asyncio
import logging
import inspect

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from memory.facts_repo import FactsRepo
from memory.episodes import EpisodesRepo
from memory.repo import MemoryRepo
from memory.chat_history import ChatHistoryRepo

from core.settings import settings
from core.logging import setup_logging

from storage.db import DB

from services.deepseek_client import DeepSeekClient
from services.world_state import WorldState

from persona.loader import PersonaManager

from orchestrator.aya_brain import AyaBrain
import orchestrator.aya_brain as _brain

from bot.routers.basic import router as basic_router
from bot.middlewares.user_context import UserContextMiddleware

import dialogue.cadence as _cad
import dialogue.humanizer as _hum

from datetime import datetime
from zoneinfo import ZoneInfo


# --- простой плейсхолдер-провайдер погоды (замени на реальный fetcher при интеграции) ---
async def fetch_spb_weather():
    return {
        "city": "Санкт-Петербург",
        "local_time_iso": datetime.now(ZoneInfo("Europe/Moscow")).isoformat(timespec="seconds"),
        "weather": {
            "temp_c": None,      # подставь фактическую температуру
            "is_rainy": False,   # подставь фактический флаг дождя
        },
    }


async def app():
    # Логи
    setup_logging(settings.LOG_LEVEL)
    log = logging.getLogger("main")

    # Диагностика модулей (в debug-лог)
    log.debug("cadence.py -> %s", inspect.getfile(_cad))
    log.debug("humanizer.py -> %s", inspect.getfile(_hum))
    log.debug("aya_brain.py -> %s", inspect.getfile(_brain))
    for mod in (_cad, _hum, _brain):
        try:
            src = inspect.getsource(mod)
            log.debug("%s len=%d hash=%d", mod.__name__, len(src), hash(src))
        except Exception as e:
            log.debug("source read error %s %s", mod.__name__, e)

    # Sanity checks
    if not settings.TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN is missing")
    # DeepSeek API-ключ не обязателен: клиент умеет демо-ответ, /health покажет состояние

    # --- DB + repositories ---
    db = DB(settings.DB_PATH)
    await db.connect()
    memory_repo = MemoryRepo(db)
    chat_history = ChatHistoryRepo(db)
    facts_repo = FactsRepo(db)
    episodes_repo = EpisodesRepo(db)
    # --- Services ---
    deepseek = DeepSeekClient(settings.DEEPSEEK_API_KEY or None)
    world_state = WorldState(db=db, fetcher=fetch_spb_weather, ttl_sec=900)
    persona = PersonaManager()

    # --- Brain ---
    aya_brain = AyaBrain(deepseek, memory_repo, world_state, chat_history, persona, facts_repo=facts_repo, episodes_repo=episodes_repo)

    # --- Telegram ---
    bot = Bot(
        token=settings.TELEGRAM_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # --- Middleware & DI ---
    dp.update.middleware(UserContextMiddleware(memory_repo))

    # Инъекции для хендлеров (используются как параметры функций)
    dp["aya_brain"] = aya_brain
    dp["memory_repo"] = memory_repo
    dp["world_state"] = world_state
    dp["chat_history"] = chat_history
    dp["db"] = db
    dp["deepseek"] = deepseek
    dp["facts_repo"] = facts_repo
    dp["episodes_repo"] = episodes_repo
    # Роутеры
    dp.include_router(basic_router)

    log.info("Starting polling…")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        log.exception("Polling stopped due to error: %s", e)
        raise
    finally:
        # Грейсфул-шатдаун
        try:
            await deepseek.aclose()
        except Exception:
            pass
        try:
            await db.close()
        except Exception:
            pass
        try:
            await bot.session.close()
        except Exception:
            pass
        log.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(app())
