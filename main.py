# main.py
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from core.settings import settings
from core.logging import setup_logging
from storage.db import DB
from memory.repo import MemoryRepo
from memory.chat_history import ChatHistoryRepo
from services.deepseek_client import DeepSeekClient
from services.world_state import WorldState
from persona.loader import PersonaManager
from orchestrator.aya_brain import AyaBrain
from bot.routers.basic import router as basic_router
from bot.middlewares.user_context import UserContextMiddleware

import inspect, dialogue.cadence as _cad, dialogue.humanizer as _hum, orchestrator.aya_brain as _brain
print("[AYA] cadence.py ->", inspect.getfile(_cad))
print("[AYA] humanizer.py ->", inspect.getfile(_hum))
print("[AYA] aya_brain.py ->", inspect.getfile(_brain))
for mod in (_cad, _hum, _brain):
    try:
        src = inspect.getsource(mod)
        print(f"[AYA] {mod.__name__} len={len(src)} hash={hash(src)}")
    except Exception as e:
        print("[AYA] source read error", mod.__name__, e)


async def app():
    setup_logging(settings.LOG_LEVEL)
    log = logging.getLogger("main")

    # --- sanity checks ---
    if not settings.TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN is missing")
    if not settings.DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY is missing")

    # --- DB + repositories ---
    db = DB(settings.DB_PATH)
    await db.connect()
    memory_repo = MemoryRepo(db)
    chat_history = ChatHistoryRepo(db)

    # --- Services ---
    deepseek = DeepSeekClient(settings.DEEPSEEK_API_KEY)
    world_state = WorldState(db)
    persona = PersonaManager()

    # --- Brain ---
    aya_brain = AyaBrain(deepseek, memory_repo, world_state, chat_history, persona)

    # --- Telegram ---
    bot = Bot(
        token=settings.TELEGRAM_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()  # ← создаём до использования

    # --- Middleware & DI ---
    dp.update.middleware(UserContextMiddleware(memory_repo))
    dp["aya_brain"] = aya_brain
    dp["memory_repo"] = memory_repo
    dp["world_state"] = world_state
    dp["chat_history"] = chat_history

    # --- Routers ---
    dp.include_router(basic_router)

    log.info("Starting polling…")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        log.exception("Polling stopped due to error: %s", e)
        raise
    finally:
        await deepseek.aclose()
        await db.close()
        try:
            await bot.session.close()
        except Exception:
            pass
        log.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(app())
