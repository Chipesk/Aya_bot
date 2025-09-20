from __future__ import annotations

import time
from pathlib import Path
from sqlite3 import OperationalError
from typing import Optional

import aiosqlite
from aiosqlite import Connection, Row


class DB:
    """Thin async wrapper around a SQLite database using :mod:`aiosqlite`."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.conn: Optional[Connection] = None
        self._schema_ready = False
        self._chat_fts_enabled = False

    async def connect(self) -> None:
        """Open a connection and initialise the schema if necessary."""
        if self.conn is not None:
            return

        if self.path.parent and not self.path.parent.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = Row
        await self.conn.execute("PRAGMA foreign_keys=ON;")
        await self.conn.execute("PRAGMA journal_mode=WAL;")
        await self.conn.execute("PRAGMA synchronous=NORMAL;")
        await self.conn.execute("PRAGMA temp_store=MEMORY;")
        await self._ensure_schema()

    async def close(self) -> None:
        if self.conn is None:
            return
        await self.conn.close()
        self.conn = None
        self._schema_ready = False
        self._chat_fts_enabled = False

    async def add_chat_message(self, user_id: int, role: str, content: str) -> int:
        if self.conn is None:
            raise RuntimeError("Database is not connected")
        await self._ensure_schema()
        now = time.time()
        cur = await self.conn.execute(
            """
            INSERT INTO chat_history(user_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, role, content, now),
        )
        message_id = cur.lastrowid
        await cur.close()
        await self.conn.commit()
        if message_id is None:
            raise RuntimeError("Failed to obtain chat_history row id")
        return int(message_id)

    async def _ensure_schema(self) -> None:
        if self.conn is None:
            raise RuntimeError("Database is not connected")
        if self._schema_ready:
            return

        async def _table_columns(table: str) -> set[str]:
            cur = await self.conn.execute(f"PRAGMA table_info('{table}')")
            rows = await cur.fetchall()
            await cur.close()
            return {row["name"] for row in rows}

        users_columns = await _table_columns("users")
        memories_columns = await _table_columns("memories")

        if users_columns and "updated_at" not in users_columns:
            await self.conn.execute("DROP TRIGGER IF EXISTS users_touch")
            await self.conn.execute("DROP TRIGGER IF EXISTS users_set_updated_at")
            await self.conn.execute("ALTER TABLE users ADD COLUMN updated_at REAL")
            await self.conn.execute(
                "UPDATE users SET updated_at = strftime('%s','now') WHERE updated_at IS NULL"
            )

        if memories_columns and "updated_at" not in memories_columns:
            await self.conn.execute("DROP TRIGGER IF EXISTS memories_touch")
            await self.conn.execute("DROP TRIGGER IF EXISTS memories_set_updated_at")
            await self.conn.execute("ALTER TABLE memories ADD COLUMN updated_at REAL")
            await self.conn.execute(
                "UPDATE memories SET updated_at = strftime('%s','now') WHERE updated_at IS NULL"
            )

        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                tg_user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                locale TEXT,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            )
            """
        )
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_user_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                UNIQUE(tg_user_id, kind, key)
            )
            """
        )
        await self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(tg_user_id)"
        )
        await self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind)"
        )

        await self.conn.execute("DROP TRIGGER IF EXISTS users_touch")
        await self.conn.execute(
            """
            CREATE TRIGGER users_touch AFTER UPDATE ON users
            WHEN NEW.updated_at = OLD.updated_at
            BEGIN
                UPDATE users SET updated_at = strftime('%s','now')
                WHERE tg_user_id = NEW.tg_user_id;
            END;
            """
        )
        await self.conn.execute("DROP TRIGGER IF EXISTS users_set_updated_at")
        await self.conn.execute(
            """
            CREATE TRIGGER users_set_updated_at AFTER INSERT ON users
            WHEN NEW.updated_at IS NULL
            BEGIN
                UPDATE users SET updated_at = strftime('%s','now')
                WHERE tg_user_id = NEW.tg_user_id;
            END;
            """
        )
        await self.conn.execute("DROP TRIGGER IF EXISTS memories_touch")
        await self.conn.execute(
            """
            CREATE TRIGGER memories_touch AFTER UPDATE ON memories
            WHEN NEW.updated_at = OLD.updated_at
            BEGIN
                UPDATE memories SET updated_at = strftime('%s','now')
                WHERE id = NEW.id;
            END;
            """
        )
        await self.conn.execute("DROP TRIGGER IF EXISTS memories_set_updated_at")
        await self.conn.execute(
            """
            CREATE TRIGGER memories_set_updated_at AFTER INSERT ON memories
            WHEN NEW.updated_at IS NULL
            BEGIN
                UPDATE memories SET updated_at = strftime('%s','now')
                WHERE id = NEW.id;
            END;
            """
        )

        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )

        try:
            await self.conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS chat_history_fts
                USING fts5(content, role, user_id UNINDEXED, message_id UNINDEXED, tokenize='unicode61')
                """
            )
            self._chat_fts_enabled = True
        except OperationalError:
            self._chat_fts_enabled = False

        if self._chat_fts_enabled:
            await self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS chat_history_ai AFTER INSERT ON chat_history BEGIN
                    INSERT INTO chat_history_fts(rowid, content, role, user_id, message_id)
                    VALUES (new.id, new.content, new.role, new.user_id, new.id);
                END;
                """
            )
            await self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS chat_history_au AFTER UPDATE ON chat_history BEGIN
                    INSERT INTO chat_history_fts(chat_history_fts, rowid)
                    VALUES ('delete', old.id);
                    INSERT INTO chat_history_fts(rowid, content, role, user_id, message_id)
                    VALUES (new.id, new.content, new.role, new.user_id, new.id);
                END;
                """
            )
            await self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS chat_history_ad AFTER DELETE ON chat_history BEGIN
                    INSERT INTO chat_history_fts(chat_history_fts, rowid)
                    VALUES ('delete', old.id);
                END;
                """
            )

        await self.conn.commit()
        self._schema_ready = True


async def ensure_db_ready(db: DB) -> DB:
    await db.connect()
    return db
