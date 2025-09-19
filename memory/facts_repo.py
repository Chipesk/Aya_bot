# memory/facts_repo.py
import json
import time
from typing import Iterable, Optional

class FactsRepo:
    """
    Универсальное KV-трипловое хранилище фактов о пользователе:
    (subject, predicate, object) + тип, единицы, уверенность, время, источник.
    Ничего не «жёстко зашито»: любые предикаты и значения.
    """
    def __init__(self, db):
        self.db = db
        self._ready = False

    async def _ensure_table(self):
        if self._ready:
            return
        await self.db.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mem_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subject TEXT NOT NULL DEFAULT 'user',
                predicate TEXT NOT NULL,
                object TEXT NOT NULL,
                dtype TEXT,
                unit TEXT,
                confidence REAL NOT NULL DEFAULT 0.7,
                source TEXT,
                source_msg_id INTEGER,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                last_seen_at REAL NOT NULL,
                expires_at REAL,
                UNIQUE(user_id, subject, predicate, object)
            )
            """
        )
        await self.db.conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_mem_facts_user_pred ON mem_facts(user_id, predicate)"
        )
        await self.db.conn.commit()
        self._ready = True

    async def upsert_fact(
        self,
        user_id: int,
        predicate: str,
        obj: str,
        *,
        subject: str = "user",
        dtype: Optional[str] = None,
        unit: Optional[str] = None,
        confidence: float = 0.7,
        source: Optional[str] = "chat",
        source_msg_id: Optional[int] = None,
        ttl_sec: Optional[int] = None,
    ):
        await self._ensure_table()
        now = time.time()
        exp = (now + ttl_sec) if ttl_sec else None
        try:
            await self.db.conn.execute(
                """
                INSERT INTO mem_facts
                (user_id, subject, predicate, object, dtype, unit, confidence, source, source_msg_id,
                 created_at, updated_at, last_seen_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, subject, predicate, str(obj), dtype, unit, float(confidence), source, source_msg_id,
                 now, now, now, exp),
            )
        except Exception:
            # уже существует — обновим уверенность (макс), время и пр.
            await self.db.conn.execute(
                """
                UPDATE mem_facts
                SET confidence = CASE WHEN confidence > ? THEN confidence ELSE ? END,
                    dtype = COALESCE(?, dtype),
                    unit = COALESCE(?, unit),
                    source = COALESCE(?, source),
                    source_msg_id = COALESCE(?, source_msg_id),
                    updated_at = ?,
                    last_seen_at = ?,
                    expires_at = COALESCE(?, expires_at)
                WHERE user_id=? AND subject=? AND predicate=? AND object=?
                """,
                (float(confidence), float(confidence), dtype, unit, source, source_msg_id,
                 now, now, exp, user_id, subject, predicate, str(obj)),
            )
        await self.db.conn.commit()

    async def purge_expired(self):
        await self._ensure_table()
        now = time.time()
        await self.db.conn.execute("DELETE FROM mem_facts WHERE expires_at IS NOT NULL AND expires_at < ?", (now,))
        await self.db.conn.commit()

    async def get_facts(self, user_id: int, predicates: Optional[Iterable[str]] = None):
        await self._ensure_table()
        if predicates:
            qs = ",".join("?" for _ in predicates)
            cur = await self.db.conn.execute(
                f"SELECT subject, predicate, object, dtype, unit, confidence, last_seen_at FROM mem_facts "
                f"WHERE user_id=? AND predicate IN ({qs}) ORDER BY confidence DESC, last_seen_at DESC",
                (user_id, *predicates),
            )
        else:
            cur = await self.db.conn.execute(
                "SELECT subject, predicate, object, dtype, unit, confidence, last_seen_at "
                "FROM mem_facts WHERE user_id=? ORDER BY confidence DESC, last_seen_at DESC",
                (user_id,),
            )
        rows = await cur.fetchall()
        return [
            {
                "subject": r[0],
                "predicate": r[1],
                "object": r[2],
                "dtype": r[3],
                "unit": r[4],
                "confidence": float(r[5]),
                "last_seen_at": float(r[6]) if r[6] is not None else None,
            }
            for r in rows
        ]

    async def top_facts(self, user_id: int, limit: int = 12):
        """
        Возвращаем топ по взвешенному скору: confidence * свежесть.
        Свежесть = 1 / (1 + дни_с_последнего_упоминания)
        """
        await self._ensure_table()
        cur = await self.db.conn.execute(
            "SELECT predicate, object, dtype, unit, confidence, last_seen_at "
            "FROM mem_facts WHERE user_id=?",
            (user_id,),
        )
        import math
        items = []
        now = time.time()
        for p, o, dt, unit, conf, seen in await cur.fetchall():
            days = max(0.0, (now - float(seen or now)) / 86400.0)
            fresh = 1.0 / (1.0 + days)
            score = float(conf or 0.5) * fresh
            items.append((score, {"predicate": p, "object": o, "dtype": dt, "unit": unit}))
        items.sort(key=lambda x: x[0], reverse=True)
        return [it[1] for it in items[:limit]]
