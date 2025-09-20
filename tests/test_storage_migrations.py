from __future__ import annotations

import sqlite3

import pytest

from memory.repo import MemoryRepo
from storage.db import DB, ensure_db_ready


@pytest.mark.asyncio
async def test_updated_at_migration(tmp_path) -> None:
    db_path = tmp_path / "legacy.db"

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE users (
            tg_user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            locale TEXT,
            created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
            UNIQUE(tg_user_id, kind, key)
        )
        """
    )
    cur.execute(
        "INSERT INTO users (tg_user_id, username, first_name, last_name, locale) VALUES (?, ?, ?, ?, ?)",
        (1, "old", "Old", "User", "en"),
    )
    cur.execute(
        "INSERT INTO memories (tg_user_id, kind, key, value) VALUES (?, ?, ?, ?)",
        (1, "facts", "nickname", "Aya"),
    )
    conn.commit()
    conn.close()

    db = DB(db_path)
    await ensure_db_ready(db)

    cur = await db.conn.execute("PRAGMA table_info('users')")
    user_columns = {row["name"] for row in await cur.fetchall()}
    await cur.close()
    assert "updated_at" in user_columns

    cur = await db.conn.execute("PRAGMA table_info('memories')")
    memory_columns = {row["name"] for row in await cur.fetchall()}
    await cur.close()
    assert "updated_at" in memory_columns

    cur = await db.conn.execute("SELECT updated_at FROM users WHERE tg_user_id=1")
    assert (await cur.fetchone())["updated_at"] is not None
    await cur.close()

    cur = await db.conn.execute("SELECT updated_at FROM memories WHERE tg_user_id=1")
    assert (await cur.fetchone())["updated_at"] is not None
    await cur.close()

    repo = MemoryRepo(db)
    await repo.ensure_user(1, "new", "New", "Name", "en")
    await repo.ensure_user(2, "second", None, None, None)

    cur = await db.conn.execute("SELECT updated_at FROM users WHERE tg_user_id=2")
    assert (await cur.fetchone())["updated_at"] is not None
    await cur.close()

    await db.close()
