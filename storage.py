"""
Хранилище общих заметок по сделкам.
Все пользователи бота видят одни и те же заметки по одной и той же сделке.
"""

import os
import sqlite3
from datetime import datetime
from contextlib import closing

# На Render укажите здесь путь на смонтированный Persistent Disk,
# например /var/data/notes.db — иначе заметки будут теряться при redeploy.
DB_PATH = os.getenv("DB_PATH", "notes.db")


def init_db() -> None:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deal_id INTEGER NOT NULL,
                author_name TEXT NOT NULL,
                author_tg_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def add_note(deal_id: int, author_name: str, author_tg_id: int, text: str) -> None:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            "INSERT INTO notes (deal_id, author_name, author_tg_id, text, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (deal_id, author_name, author_tg_id, text, datetime.now().strftime("%d.%m.%Y %H:%M")),
        )
        conn.commit()


def get_notes(deal_id: int) -> list[tuple[str, str, str]]:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute(
            "SELECT author_name, text, created_at FROM notes WHERE deal_id = ? ORDER BY id ASC",
            (deal_id,),
        )
        return cur.fetchall()
