# mypy: ignore-errors
# memory/facts_repo.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from sqlite3 import OperationalError
import time
import re

_TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+", re.UNICODE)

def _fts_phrase(text: str, max_tokens: int = 8) -> Optional[str]:
    toks = _TOKEN_RE.findall(text or "")
    if not toks:
        return None
    phrase = " ".join(toks[:max_tokens]).replace('"','""')
    return f'"{phrase}"' if phrase else None

class FactsRepo:
    """
    Универсальные факты про пользователя, БЕЗ whitelist.
    Таблица:
      facts(
        id INTEGER PK AUTOINCREMENT,
        tg_user_id INTEGER NOT NULL,
        predicate TEXT NOT NULL,   -- произвольный ключ (e.g., "pets", "work_place", "loves_fish")
        object TEXT NOT NULL,      -- произвольное значение
        confidence REAL NOT NULL,  -- 0..1
        source_msg_id INTEGER NULL,
        updated_at REAL NOT NULL,
        created_at REAL NOT NULL
      )
    FTS: facts_fts(predicate, object) для поиска/слияния.
    """

    def __init__(self, db: Any):
        if not hasattr(db, "conn"):
            raise ValueError("FactsRepo expects db.conn")
        self.db = db
        self._ready = False
        self._table = "facts"
        self._fts = "facts_fts"

    async def _ensure(self):
        if self._ready:
            return
        await self.db.conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {self._table}(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          tg_user_id INTEGER NOT NULL,
          predicate TEXT NOT NULL,
          object TEXT NOT NULL,
          confidence REAL NOT NULL,
          source_msg_id INTEGER NULL,
          updated_at REAL NOT NULL,
          created_at REAL NOT NULL
        );
        """)
        await self.db.conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{self._table}_user ON {self._table}(tg_user_id);")
        await self.db.conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{self._table}_pred ON {self._table}(predicate);")
        # FTS
        await self.db.conn.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS {self._fts}
        USING fts5(predicate, object, tg_user_id UNINDEXED, fact_id UNINDEXED, tokenize='unicode61');
        """)
        # триггеры синхры
        await self.db.conn.execute(f"""
        CREATE TRIGGER IF NOT EXISTS {self._table}_ai AFTER INSERT ON {self._table} BEGIN
          INSERT INTO {self._fts}(rowid, predicate, object, tg_user_id, fact_id)
          VALUES (new.id, new.predicate, new.object, new.tg_user_id, new.id);
        END;""")
        await self.db.conn.execute(f"""
        CREATE TRIGGER IF NOT EXISTS {self._table}_ad AFTER DELETE ON {self._table} BEGIN
          INSERT INTO {self._fts}({self._fts}, rowid) VALUES ('delete', old.id);
        END;""")
        await self.db.conn.execute(f"""
        CREATE TRIGGER IF NOT EXISTS {self._table}_au AFTER UPDATE ON {self._table} BEGIN
          INSERT INTO {self._fts}({self._fts}, rowid) VALUES ('delete', old.id);
          INSERT INTO {self._fts}(rowid, predicate, object, tg_user_id, fact_id)
          VALUES (new.id, new.predicate, new.object, new.tg_user_id, new.id);
        END;""")
        await self.db.conn.commit()
        self._ready = True

    # --------- CRUD / UPSERT ---------

    async def upsert_many(self, tg_user_id: int, facts: List[Dict], source_msg_id: Optional[int] = None):
        """
        facts: [{predicate, object, confidence}]
        Без whitelist. Нормализуем, режем слишком длинное, апдейтим confidence (max/EMA).
        """
        await self._ensure()
        now = time.time()
        # упрощённый дедуп по (predicate, object)
        for f in facts:
            pred = (f.get("predicate") or "").strip()
            obj  = (f.get("object") or "").strip()
            conf = float(f.get("confidence") or 0.0)
            if not pred or not obj:
                continue
            if conf < 0.4:  # мягкий порог, можно настроить
                continue
            if len(pred) > 128 or len(obj) > 2048:
                continue

            # пробуем найти близкий факт (точное совпадение для простоты)
            cur = await self.db.conn.execute(
                f"SELECT id, confidence FROM {self._table} WHERE tg_user_id=? AND predicate=? AND object=? LIMIT 1",
                (tg_user_id, pred, obj)
            )
            row = await cur.fetchone()
            await cur.close()
            if row:
                fact_id, old_conf = row[0], float(row[1])
                new_conf = max(old_conf, conf)  # можно сделать EMA:  new = 0.7*old + 0.3*conf
                await self.db.conn.execute(
                    f"UPDATE {self._table} SET confidence=?, updated_at=? WHERE id=?",
                    (new_conf, now, fact_id)
                )
            else:
                await self.db.conn.execute(
                    f"""INSERT INTO {self._table}(tg_user_id, predicate, object, confidence, source_msg_id, updated_at, created_at)
                        VALUES(?,?,?,?,?,?,?)""",
                    (tg_user_id, pred, obj, conf, source_msg_id, now, now)
                )
        await self.db.conn.commit()

    async def get_all(self, tg_user_id: int, limit: int = 200) -> List[Dict]:
        await self._ensure()
        cur = await self.db.conn.execute(
            f"""SELECT id, predicate, object, confidence, source_msg_id, created_at, updated_at
                FROM {self._table}
                WHERE tg_user_id=?
                ORDER BY updated_at DESC, confidence DESC
                LIMIT ?""",
            (tg_user_id, limit)
        )
        rows = await cur.fetchall()
        await cur.close()
        return [
            {
                "id": r[0], "predicate": r[1], "object": r[2],
                "confidence": float(r[3]), "source_msg_id": r[4],
                "created_at": r[5], "updated_at": r[6]
            } for r in rows
        ]

    async def search(self, tg_user_id: int, query: str, limit: int = 20) -> List[Dict]:
        await self._ensure()
        q = (query or "").strip()
        if not q:
            return []
        phrase = _fts_phrase(q, 8)
        if phrase:
            try:
                cur = await self.db.conn.execute(
                    f"""SELECT f.id, f.predicate, f.object, f.confidence, f.source_msg_id, f.created_at, f.updated_at
                        FROM {self._fts} x
                        JOIN {self._table} f ON f.id = x.rowid
                        WHERE f.tg_user_id=? AND {self._fts} MATCH ?
                        ORDER BY bm25({self._fts})
                        LIMIT ?""",
                    (tg_user_id, phrase, limit)
                )
                rows = await cur.fetchall()
                await cur.close()
                if rows:
                    return [
                        {"id": r[0], "predicate": r[1], "object": r[2],
                         "confidence": float(r[3]), "source_msg_id": r[4],
                         "created_at": r[5], "updated_at": r[6]}
                        for r in rows
                    ]
            except OperationalError:
                pass
        # fallback LIKE
        cur = await self.db.conn.execute(
            f"""SELECT id, predicate, object, confidence, source_msg_id, created_at, updated_at
                FROM {self._table}
                WHERE tg_user_id=? AND (predicate LIKE ? OR object LIKE ?)
                ORDER BY updated_at DESC
                LIMIT ?""",
            (tg_user_id, f"%{q}%", f"%{q}%", limit)
        )
        rows = await cur.fetchall()
        await cur.close()
        return [
            {"id": r[0], "predicate": r[1], "object": r[2],
             "confidence": float(r[3]), "source_msg_id": r[4],
             "created_at": r[5], "updated_at": r[6]}
            for r in rows
        ]
