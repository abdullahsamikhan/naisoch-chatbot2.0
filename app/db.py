"""
Thin sqlite3 wrappers. No ORM - this app has two tiny tables and doesn't
need SQLAlchemy's overhead for an MVP this size.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connect(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_token_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shopify_tokens (
                shop TEXT PRIMARY KEY,
                access_token TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )


def init_catalog_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                row_index INTEGER PRIMARY KEY,
                product_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                handle TEXT,
                price TEXT,
                currency TEXT,
                available INTEGER,
                image_url TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
