# memory/episodes.py
import time, re
from typing import List, Dict, Optional
from sqlite3 import OperationalError

_TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+", re.UNICODE)
def _fts_phrase(text: str, max_tokens: int = 8) -> Optional[str]:
    toks = _TOKEN_RE.findall(text or "")
    if not toks: return None
    phrase = " ".join(toks[:max_tokens]).replace('"', '""')
    return f'"{phrase}"' if phrase else None

class EpisodesRepo:
    def __init__(self, db):
        self.db = db
        self._ready = False

    async def _ensure(self):
        if self._ready: return
        await self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS mem_episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                turn_start INTEGER,
                turn_end INTEGER,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )""")
        await self.db.conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS mem_episodes_fts
            USING fts5(title, summary, user_id UNINDEXED, episode_id UNINDEXED, tokenize='unicode61')
        """)
        # триггеры синхронизации
        await self.db.conn.execute("""
            CREATE TRIGGER IF NOT EXISTS mem_episodes_ai AFTER INSERT ON mem_episodes BEGIN
                INSERT INTO mem_episodes_fts(rowid, title, summary, user_id, episode_id)
                VALUES (new.id, new.title, new.summary, new.user_id, new.id);
            END;""")
        await self.db.conn.execute("""
            CREATE TRIGGER IF NOT EXISTS mem_episodes_ad AFTER DELETE ON mem_episodes BEGIN
                INSERT INTO mem_episodes_fts(mem_episodes_fts, rowid)
                VALUES ('delete', old.id);
            END;""")
        await self.db.conn.execute("""
            CREATE TRIGGER IF NOT EXISTS mem_episodes_au AFTER UPDATE ON mem_episodes BEGIN
                INSERT INTO mem_episodes_fts(mem_episodes_fts, rowid)
                VALUES ('delete', old.id);
                INSERT INTO mem_episodes_fts(rowid, title, summary, user_id, episode_id)
                VALUES (new.id, new.title, new.summary, new.user_id, new.id);
            END;""")
        await self.db.conn.commit()
        self._ready = True

    async def add(self, user_id: int, title: str, summary: str,
                  turn_start: int|None=None, turn_end: int|None=None) -> int:
        await self._ensure()
        now = time.time()
        cur = await self.db.conn.execute(
            "INSERT INTO mem_episodes(user_id,title,summary,turn_start,turn_end,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (user_id, title, summary, turn_start, turn_end, now, now)
        )
        await self.db.conn.commit()
        return cur.lastrowid

    async def search(self, user_id: int, query: str, limit: int = 3) -> List[Dict]:
        await self._ensure()
        q = (query or "").strip()
        if not q: return []
        phrase = _fts_phrase(q, 8)
        if phrase:
            try:
                cur = await self.db.conn.execute(
                    "SELECT episode_id, title, summary FROM mem_episodes_fts "
                    "WHERE mem_episodes_fts MATCH ? AND user_id=? "
                    "ORDER BY bm25(mem_episodes_fts) LIMIT ?",
                    (phrase, user_id, limit),
                )
                rows = await cur.fetchall(); await cur.close()
                if rows:
                    return [{"id": r[0], "title": r[1], "summary": r[2]} for r in rows]
            except OperationalError:
                pass
        # Fallback LIKE
        cur = await self.db.conn.execute(
            "SELECT id, title, summary FROM mem_episodes "
            "WHERE user_id=? AND (title LIKE ? OR summary LIKE ?) "
            "ORDER BY id DESC LIMIT ?",
            (user_id, f"%{q}%", f"%{q}%", limit)
        )
        rows = await cur.fetchall(); await cur.close()
        return [{"id": r[0], "title": r[1], "summary": r[2]} for r in rows]
