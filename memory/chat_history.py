# memory/chat_history.py
from typing import List, Dict

class ChatHistoryRepo:
    def __init__(self, db):
        self.db = db

    async def add(self, tg_user_id: int, role: str, content: str):
        await self.db.conn.execute(
            "INSERT INTO messages (tg_user_id, role, content) VALUES (?, ?, ?)",
            (tg_user_id, role, content),
        )
        await self.db.conn.commit()

    async def last(self, tg_user_id: int, limit: int = 10) -> List[Dict]:
        cur = await self.db.conn.execute(
            "SELECT role, content FROM messages WHERE tg_user_id=? ORDER BY id DESC LIMIT ?",
            (tg_user_id, limit),
        )
        rows = await cur.fetchall()
        rows.reverse()
        return [{"role": r[0], "content": r[1]} for r in rows]
