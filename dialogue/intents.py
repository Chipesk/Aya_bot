import re
from typing import Dict

# Рус/Eng варианты триггеров
MEMORY_TRIGGERS = [
    r"\b(память|помнишь|что ты помнишь|что запомнила|сводку памяти|обзор памяти|memory overview|show memory|what do you remember)\b",
    r"\b(покажи|дай)\s+(мне\s+)?(сводку|обзор)\s+памяти\b",
    r"\b(что ты про меня помнишь|что ты про нас помнишь)\b",
]

def detect_intents(text: str) -> Dict[str, bool]:
    t = (text or "").lower().strip()
    user_asked_memory_overview = any(re.search(p, t) for p in MEMORY_TRIGGERS)
    # тут же можно добавлять другие интенты, например:
    # user_asked_schedule = ...
    return {
        "user_asked_memory_overview": bool(user_asked_memory_overview),
    }
