# dialogue/greeting.py
import re
from datetime import datetime
from zoneinfo import ZoneInfo

HELLO_RE = re.compile(
    r"^(привет|здравствуй|доброе утро|добрый день|добрый вечер|hi|hello)\b", re.IGNORECASE
)

def is_user_greeting(text: str) -> bool:
    return bool(HELLO_RE.search((text or "").strip()))

def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None

def greeting_policy(
    now: datetime,
    last_bot_greet_iso: str | None,
    daily_greet_count: int,
    user_greeted: bool,
    turn: int,
    idle_seconds: int | None,
):
    """
    Возвращает dict с флагами:
    - allow: можно ли начинать с приветствия
    - kind: 'ack' (краткое «угу» на привет), 'short', 'warm', 'none'
    """
    if daily_greet_count >= 3:
        return {"allow": False, "kind": "none"}

    # Новая беседа (самое начало) — можно коротко
    if turn <= 2 and not last_bot_greet_iso:
        return {"allow": True, "kind": "short"}

    # Если пользователь явно поздоровался
    if user_greeted:
        # Если бот только что здоровался — отвечаем без «Привет», просто короткое признание
        if idle_seconds is not None and idle_seconds < 15 * 60:
            return {"allow": False, "kind": "ack"}
        return {"allow": True, "kind": "short"}

    # Длинная пауза — допустим тёплый ре-энтри
    if idle_seconds is not None and idle_seconds >= 3 * 60 * 60:
        return {"allow": True, "kind": "warm"}

    # По умолчанию — без приветствия
    return {"allow": False, "kind": "none"}

def is_bot_greeting(text: str) -> bool:
    # на всякий случай проверяем исходящий текст
    return bool(HELLO_RE.search((text or "").strip()))
