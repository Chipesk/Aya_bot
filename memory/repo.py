# memory/repo.py
from typing import Optional
import logging
import json
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger("memory")

SUSPICIOUS_NAMES = {s.casefold() for s in [
    "слушаю", "запомнила", "сегодня", "дата", "время", "привет", "ок", "ага"
]}

def _now_iso() -> str:
    return datetime.now(ZoneInfo("Europe/Moscow")).isoformat(timespec="seconds")

def _today_key() -> str:
    return datetime.now().strftime("%Y%m%d")


class MemoryRepo:
    def __init__(self, db):
        self.db = db

    # --- Flirt / Intimacy state ---
    ALLOWED_FLIRT_LEVELS = {"off", "soft", "romantic", "suggestive", "roleplay"}

    async def get_adult_confirmed(self, tg_user_id: int) -> bool:
        return (await self.get_kv(tg_user_id, "intimacy", "adult_confirmed")) == "1"

    async def set_adult_confirmed(self, tg_user_id: int, ok: bool):
        await self.set_kv(tg_user_id, "intimacy", "adult_confirmed", "1" if ok else "0")

    async def get_flirt_consent(self, tg_user_id: int) -> bool:
        return (await self.get_kv(tg_user_id, "intimacy", "flirt_consent")) == "1"

    async def set_flirt_consent(self, tg_user_id: int, ok: bool):
        await self.set_kv(tg_user_id, "intimacy", "flirt_consent", "1" if ok else "0")

    async def set_flirt_level(self, tg_user_id: int, level: str):
        level = (level or "off").strip().lower()
        if level not in self.ALLOWED_FLIRT_LEVELS:
            level = "off"
        await self.set_kv(tg_user_id, "flirt", "level", level)

    async def get_flirt_level(self, tg_user_id: int) -> str:
        v = await self.get_kv(tg_user_id, "flirt", "level")
        return v if v in self.ALLOWED_FLIRT_LEVELS else "off"

    async def ensure_user(self, tg_user_id: int, username: Optional[str], first: Optional[str], last: Optional[str], locale: Optional[str]):
        await self.db.conn.execute(
            """
            INSERT INTO users (tg_user_id, username, first_name, last_name, locale)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(tg_user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                locale=excluded.locale
            """,
            (tg_user_id, username, first, last, locale),
        )
        await self.db.conn.commit()

    async def set_kv(self, tg_user_id: int, kind: str, key: str, value: str):
        await self.db.conn.execute(
            """
            INSERT INTO memories (tg_user_id, kind, key, value)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(tg_user_id, kind, key) DO UPDATE SET value=excluded.value
            """,
            (tg_user_id, kind, key, value),
        )
        await self.db.conn.commit()

    async def get_kv(self, tg_user_id: int, kind: str, key: str) -> Optional[str]:
        cur = await self.db.conn.execute(
            "SELECT value FROM memories WHERE tg_user_id=? AND kind=? AND key=?",
            (tg_user_id, kind, key),
        )
        row = await cur.fetchone()
        return row[0] if row else None

    async def del_kv(self, tg_user_id: int, kind: str, key: str):
        await self.db.conn.execute(
            "DELETE FROM memories WHERE tg_user_id=? AND kind=? AND key=?",
            (tg_user_id, kind, key),
        )
        await self.db.conn.commit()

    # ------- Session presence / greetings -------
    async def touch_seen(self, tg_user_id: int):
        await self.set_kv(tg_user_id, "session", "last_seen", _now_iso())

    async def get_last_seen(self, tg_user_id: int) -> Optional[str]:
        return await self.get_kv(tg_user_id, "session", "last_seen")

    async def set_last_bot_greet_at(self, tg_user_id: int, iso: str | None = None):
        if iso is None:
            await self.del_kv(tg_user_id, "session", "last_bot_greet_at")
        else:
            await self.set_kv(tg_user_id, "session", "last_bot_greet_at", iso)

    async def get_last_bot_greet_at(self, tg_user_id: int) -> Optional[str]:
        return await self.get_kv(tg_user_id, "session", "last_bot_greet_at")

    async def inc_daily_greet(self, tg_user_id: int, date_key: str | None = None):
        dk = date_key or _today_key()
        key = f"greet_count_{dk}"
        cur = await self.get_kv(tg_user_id, "session", key)
        try:
            val = int(cur) + 1
        except Exception:
            val = 1
        await self.set_kv(tg_user_id, "session", key, str(val))

    async def get_daily_greet(self, tg_user_id: int, date_key: str | None = None) -> int:
        dk = date_key or _today_key()
        key = f"greet_count_{dk}"
        cur = await self.get_kv(tg_user_id, "session", key)
        try:
            return int(cur)
        except (TypeError, ValueError):
            return 0

    async def reset_daily_greet(self, tg_user_id: int, date_key: str | None = None):
        dk = date_key or _today_key()
        await self.del_kv(tg_user_id, "session", f"greet_count_{dk}")

    async def set_daily_greet(self, tg_user_id: int, value: int, date_key: str | None = None):
        dk = date_key or _today_key()
        await self.set_kv(tg_user_id, "session", f"greet_count_{dk}", str(int(value)))

    # ------- Long-term facts (мульти-значения) -------
    async def add_to_set_fact(self, tg_user_id: int, key: str, value: str):
        cur = await self.get_kv(tg_user_id, "facts", key)
        try:
            s = set(json.loads(cur)) if cur else set()
        except Exception:
            s = set()
        s.add(value)
        await self.set_kv(tg_user_id, "facts", key, json.dumps(sorted(s), ensure_ascii=False))

    async def get_set_fact(self, tg_user_id: int, key: str) -> list[str]:
        cur = await self.get_kv(tg_user_id, "facts", key)
        if not cur:
            return []
        try:
            data = json.loads(cur)
            if isinstance(data, list):
                return data
            if isinstance(data, (set, tuple)):
                return list(data)
            return []
        except Exception:
            return []

    # ------- Addressing / Affinity -------
    async def get_user_affection_mode(self, tg_user_id: int) -> str:
        v = await self.get_kv(tg_user_id, "user", "affection_mode")
        return v or "none"

    async def set_user_affection_mode(self, tg_user_id: int, mode: str):
        await self.set_kv(tg_user_id, "user", "affection_mode", mode)

    async def get_affinity(self, tg_user_id: int) -> int:
        v = await self.get_kv(tg_user_id, "dialog", "affinity")
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    async def set_affinity(self, tg_user_id: int, value: int):
        v = max(-100, min(100, int(value)))
        await self.set_kv(tg_user_id, "dialog", "affinity", str(v))

    async def bump_affinity(self, tg_user_id: int, delta: int):
        cur = await self.get_affinity(tg_user_id)
        new = max(-5, min(20, cur + delta))
        await self.set_kv(tg_user_id, "dialog", "affinity", str(new))

    # ---------- USER PROFILE ----------
    async def get_user_display_name(self, tg_user_id: int):
        val = await self.get_kv(tg_user_id, "user", "display_name")
        if not val:
            return None
        v = val.strip()
        if v.casefold() in SUSPICIOUS_NAMES:
            return None
        if len(v) < 2 or len(v) > 24:
            return None
        return v

    async def set_user_display_name(self, tg_user_id: int, name: str | None):
        val = (name or "").strip()
        if not val:
            await self.del_kv(tg_user_id, "user", "display_name")
            return
        if val.casefold() in SUSPICIOUS_NAMES or len(val) < 2 or len(val) > 24:
            return
        await self.set_kv(tg_user_id, "user", "display_name", val)

    # ---------- USER PREFS ----------
    async def get_user_prefs(self, tg_user_id: int) -> dict:
        nick_ok = await self.get_kv(tg_user_id, "user", "nickname_allowed")
        nick = await self.get_kv(tg_user_id, "user", "nickname")
        formality = await self.get_kv(tg_user_id, "user", "formality")
        return {
            "nickname_allowed": (nick_ok == "1"),
            "nickname": nick if nick and nick.strip() and nick.casefold() not in SUSPICIOUS_NAMES else None,
            "formality": formality or "neutral",
        }

    async def set_user_nickname_allowed(self, tg_user_id: int, allowed: bool):
        await self.set_kv(tg_user_id, "user", "nickname_allowed", "1" if allowed else "0")

    async def set_user_nickname(self, tg_user_id: int, nickname: Optional[str]):
        nickname = (nickname or "").strip()
        if not nickname:
            await self.del_kv(tg_user_id, "user", "nickname")
            return
        await self.set_kv(tg_user_id, "user", "nickname", nickname)

    async def set_user_formality(self, tg_user_id: int, formality: str):
        await self.set_kv(tg_user_id, "user", "formality", formality)

    # ---------- DIALOG STATE / TOPIC ----------
    async def set_dialog_state(self, tg_user_id: int, intent: str, payload: str = ""):
        await self.set_kv(tg_user_id, "dialog", "last_intent", intent)
        await self.set_kv(tg_user_id, "dialog", "last_payload", payload)
        await self.set_kv(tg_user_id, "dialog", "last_intent_ts", _now_iso())

    async def get_dialog_state(self, tg_user_id: int):
        intent = await self.get_kv(tg_user_id, "dialog", "last_intent")
        payload = await self.get_kv(tg_user_id, "dialog", "last_payload")
        ts = await self.get_kv(tg_user_id, "dialog", "last_intent_ts")
        return intent, payload, ts

    async def clear_dialog_state(self, tg_user_id: int):
        await self.del_kv(tg_user_id, "dialog", "last_intent")
        await self.del_kv(tg_user_id, "dialog", "last_payload")
        await self.del_kv(tg_user_id, "dialog", "last_intent_ts")

    async def set_topic(self, tg_user_id: int, topic: str):
        await self.set_kv(tg_user_id, "dialog", "topic", topic)

    async def get_topic(self, tg_user_id: int):
        return await self.get_kv(tg_user_id, "dialog", "topic")

    # ---------- TURN COUNTER ----------
    async def inc_turn(self, tg_user_id: int) -> int:
        cur = await self.db.conn.execute(
            "SELECT value FROM memories WHERE tg_user_id=? AND kind='dialog' AND key='turn'",
            (tg_user_id,),
        )
        row = await cur.fetchone()
        n = int(row[0]) + 1 if row else 1
        await self.set_kv(tg_user_id, "dialog", "turn", str(n))
        return n

    async def get_turn(self, tg_user_id: int) -> int:
        cur = await self.db.conn.execute(
            "SELECT value FROM memories WHERE tg_user_id=? AND kind='dialog' AND key='turn'",
            (tg_user_id,),
        )
        row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def reset_turn(self, tg_user_id: int):
        await self.del_kv(tg_user_id, "dialog", "turn")

    async def remove_set_fact(self, tg_user_id: int, key: str, value: str | None = None):
        cur = await self.get_kv(tg_user_id, "facts", key)
        try:
            s = set(json.loads(cur)) if cur else set()
        except Exception:
            s = set()
        if value is None:
            await self.del_kv(tg_user_id, "facts", key)
            return
        s.discard(value)
        if s:
            await self.set_kv(tg_user_id, "facts", key, json.dumps(sorted(s)))
        else:
            await self.del_kv(tg_user_id, "facts", key)
