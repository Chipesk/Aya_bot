# mypy: ignore-errors
# services/world_state.py
import json
import time
from typing import Any, Dict, Optional


class WorldState:
    def __init__(self, db, fetcher, ttl_sec: int = 900):
        """
        db: storage.db.DB со свойством .conn (aiosqlite)
        fetcher: async callable -> dict  (фактический запрос погоды/контекста)
        """
        self.db = db
        self.fetcher = fetcher
        self.ttl_sec = ttl_sec
        self._ready = False

    async def _table_exists(self) -> bool:
        cur = await self.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='world_state'"
        )
        return (await cur.fetchone()) is not None

    async def _ensure_table(self):
        """
        Создаёт таблицу при отсутствии и мигрирует любую старую схему к:
        world_state(key TEXT UNIQUE, payload TEXT NOT NULL, updated_at REAL NOT NULL)
        """
        if self._ready:
            return

        if not await self._table_exists():
            await self.db.conn.execute(
                """
                CREATE TABLE world_state (
                    key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            await self.db.conn.commit()
            self._ready = True
            return

        # Таблица есть — проверим колонки
        cur = await self.db.conn.execute("PRAGMA table_info('world_state')")
        cols = {row[1] for row in await cur.fetchall()}  # row[1] = name

        # 1) Добавим key при отсутствии
        if "key" not in cols:
            await self.db.conn.execute("ALTER TABLE world_state ADD COLUMN key TEXT")
            # если много строк — оставим только самую свежую (по rowid)
            cur = await self.db.conn.execute("SELECT rowid FROM world_state")
            rows = [r[0] for r in await cur.fetchall()]
            if len(rows) > 1:
                await self.db.conn.execute(
                    "DELETE FROM world_state WHERE rowid NOT IN (SELECT MAX(rowid) FROM world_state)"
                )
            await self.db.conn.execute(
                "UPDATE world_state SET key=? WHERE key IS NULL", ("spb_world",)
            )
            cols.add("key")

        # 2) Добавим updated_at при отсутствии
        if "updated_at" not in cols:
            await self.db.conn.execute("ALTER TABLE world_state ADD COLUMN updated_at REAL")
            await self.db.conn.execute(
                "UPDATE world_state SET updated_at=? WHERE updated_at IS NULL",
                (time.time(),),
            )
            cols.add("updated_at")

        # 3) Уникальный индекс по key (если PK не удалось задать ранее)
        await self.db.conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_world_state_key ON world_state(key)"
        )

        await self.db.conn.commit()
        self._ready = True

    async def _get_cache(self, key: str) -> Optional[Dict[str, Any]]:
        await self._ensure_table()
        cur = await self.db.conn.execute(
            "SELECT payload, updated_at FROM world_state WHERE key=?",
            (key,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        payload_s, updated_at = row
        if updated_at is None:
            return None
        if (time.time() - float(updated_at)) > self.ttl_sec:
            return None
        try:
            return json.loads(payload_s)
        except Exception:
            return None

    async def _set_cache(self, key: str, payload: Dict[str, Any]):
        await self._ensure_table()
        await self.db.conn.execute(
            "REPLACE INTO world_state (key, payload, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(payload, ensure_ascii=False), time.time()),
        )
        await self.db.conn.commit()

    async def get_context(self) -> Dict[str, Any]:
        """
        Возвращает свежий контекст из кэша или fetcher; при сетевых ошибках
        отдаёт последний кэш (если есть), иначе деградированный ответ.
        """
        key = "spb_world"
        cached = await self._get_cache(key)
        if cached is not None:
            return cached
        try:
            fresh = await self.fetcher()
            if not isinstance(fresh, dict):
                fresh = {"raw": fresh}
            await self._set_cache(key, fresh)
            return fresh
        except Exception:
            # fallback на старый (возможно, просроченный) кэш
            try:
                cur = await self.db.conn.execute("SELECT payload FROM world_state WHERE key=?", (key,))
                row = await cur.fetchone()
                if row:
                    return json.loads(row[0])
            except Exception:
                pass
            return {"status": "degraded", "weather": None}
