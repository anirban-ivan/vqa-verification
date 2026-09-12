"""
Storage backend for the QA verification app.

Uses Supabase (Postgres) when SUPABASE_URL/SUPABASE_KEY are configured
(via Streamlit secrets or environment variables) — that's the remote,
multi-reviewer deployment. Falls back to a local SQLite file otherwise,
so the app is fully testable without any cloud account.

Both backends implement the same two operations: get_all() and upsert().
"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

LOCAL_DB_PATH = Path(__file__).parent / "local_dev.db"
TABLE = "verifications"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteStorage:
    """Local fallback store — used when no Supabase secrets are configured."""

    def __init__(self, path: Path = LOCAL_DB_PATH):
        self.path = path
        self._init()

    def _connect(self):
        return sqlite3.connect(self.path)

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    key TEXT PRIMARY KEY,
                    image_filename TEXT,
                    pair_id TEXT,
                    status TEXT,
                    correction_bn TEXT,
                    reviewer TEXT,
                    updated_at TEXT
                )
            """)

    def get_all(self) -> dict[str, dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(f"SELECT * FROM {TABLE}").fetchall()
        return {r["key"]: dict(r) for r in rows}

    def upsert(self, key: str, fields: dict) -> None:
        row = {**fields, "key": key, "updated_at": _now()}
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        updates = ", ".join(f"{c}=excluded.{c}" for c in row if c != "key")
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO {TABLE} ({cols}) VALUES ({placeholders}) "
                f"ON CONFLICT(key) DO UPDATE SET {updates}",
                list(row.values()),
            )


class SupabaseStorage:
    """Remote store backed by Supabase Postgres — used once secrets are set.

    NOTE: this path has not been exercised against a live Supabase project
    yet (built from the documented supabase-py API) — test it for real as
    soon as a project + table exist, before relying on it for the full run.
    """

    def __init__(self, url: str, key: str):
        from supabase import create_client
        self.client = create_client(url, key)

    def get_all(self) -> dict[str, dict]:
        response = self.client.table(TABLE).select("*").execute()
        return {row["key"]: row for row in response.data}

    def upsert(self, key: str, fields: dict) -> None:
        row = {**fields, "key": key, "updated_at": _now()}
        self.client.table(TABLE).upsert(row).execute()


def get_storage():
    """Supabase if secrets are configured (deployed), else local SQLite (dev)."""
    url = None
    key = None
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")
    except Exception:
        pass
    url = url or os.environ.get("SUPABASE_URL")
    key = key or os.environ.get("SUPABASE_KEY")

    if url and key:
        return SupabaseStorage(url, key)
    return SQLiteStorage()
