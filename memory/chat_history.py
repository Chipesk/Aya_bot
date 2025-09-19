# mypy: ignore-errors
# memory/chat_history.py
from __future__ import annotations
import re
from typing import Any, List, Dict, Optional
from sqlite3 import OperationalError

_TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+", re.UNICODE)

def _fts_phrase(text: str, max_tokens: int = 8) -> Optional[str]:
    toks = _TOKEN_RE.findall(text or "")
    if not toks:
        return None
    phrase = " ".join(toks[:max_tokens]).replace('"', '""')
    return f'"{phrase}"' if phrase else None

class ChatHistoryRepo:
    def __init__(self, db: Any):
        if not hasattr(db, "conn"):
            raise ValueError("ChatHistoryRepo expects db.conn")
        self.db = db
        self._init_done = False
        self._table = "chat_history"
        self._text_col = "content"
        self._fts_table = "chat_history_fts"

    async def _ensure(self):
        if self._init_done:
            return
        # Определяем что реально есть
        tbls = {r[0] for r in await (await self.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )).fetchall()}
        if "chat_history" in tbls:
            self._table = "chat_history"
        elif "messages" in tbls:
            self._table = "messages"
        # Определяем столбец текста
        cols = [r[1].lower() for r in await (await self.db.conn.execute(
            f"PRAGMA table_info({self._table})"
        )).fetchall()]
        for cand in ("content", "text", "body", "message", "msg", "payload"):
            if cand in cols:
                self._text_col = cand
                break
        # FTS-таблица, если есть
        fts_name = f"{self._table}_fts" if f"{self._table}_fts" in tbls else \
                   (self._fts_table if self._fts_table in tbls else None)
        self._fts_table = fts_name or ""
        self._init_done = True

    async def last(self, user_id: int, limit: int = 8) -> List[Dict]:
        await self._ensure()
        cur = await self.db.conn.execute(
            f"""
            SELECT id, role, {self._text_col} AS content, created_at
            FROM (
                SELECT id, role, {self._text_col}, created_at
                FROM {self._table}
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
            ) t
            ORDER BY id ASC
            """,
            (user_id, limit),
        )
        rows = await cur.fetchall()
        await cur.close()
        return [{"id": r[0], "role": r[1], "content": r[2], "created_at": r[3]} for r in rows]

    async def search_text(self, user_id: int, user_text: str, limit: int = 4) -> List[Dict]:
        await self._ensure()
        q = (user_text or "").strip()
        if not q:
            return []
        # Пробуем FTS, если есть виртуальная таблица
        if self._fts_table:
            phrase = _fts_phrase(q, 8)
            if phrase:
                try:
                    cur = await self.db.conn.execute(
                        f"""
                        SELECT m.id, m.role, m.{self._text_col} AS content, m.created_at
                        FROM {self._fts_table} f
                        JOIN {self._table} m ON m.id = f.rowid
                        WHERE m.user_id = ? AND {self._fts_table} MATCH ?
                        ORDER BY rank
                        LIMIT ?
                        """,
                        (user_id, phrase, limit),
                    )
                    rows = await cur.fetchall()
                    await cur.close()
                    if rows:
                        return [{"id": r[0], "role": r[1], "content": r[2], "created_at": r[3]} for r in rows]
                except OperationalError:
                    pass
        # fallback → LIKE
        cur = await self.db.conn.execute(
            f"""
            SELECT id, role, {self._text_col} AS content, created_at
            FROM {self._table}
            WHERE user_id = ? AND {self._text_col} LIKE ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, f"%{q}%", limit),
        )
        rows = await cur.fetchall()
        await cur.close()
        return [{"id": r[0], "role": r[1], "content": r[2], "created_at": r[3]} for r in rows]
