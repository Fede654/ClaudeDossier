"""Reads Codex CLI thread metadata from state_5.sqlite."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path.home() / ".codex" / "state_5.sqlite"

_QUERY = """
SELECT id, rollout_path, created_at, updated_at, cwd, title,
       git_branch, git_sha, first_user_message, tokens_used
FROM threads
WHERE archived = 0
ORDER BY updated_at DESC
"""


def load_codex_threads(db_path: Path | None = None) -> list[dict]:
    """Return a list of non-archived thread dicts from Codex state_5.sqlite."""
    path = db_path or _DEFAULT_DB
    if not path.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(_QUERY).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Cannot read Codex SQLite %s: %s", path, e)
        return []
