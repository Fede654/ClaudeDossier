"""SQLite FTS5 full-text search index for session content."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)
DB_PATH = Path.home() / ".cache" / "claude-dossier" / "search.db"


def _extract_text(jsonl_path: Path) -> str:
    """Extract user/assistant message text from a JSONL file."""
    parts = []
    try:
        with jsonl_path.open(errors='replace') as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get('type') not in ('user', 'assistant'):
                    continue
                content = obj.get('message', {}).get('content', '')
                if isinstance(content, str):
                    if content:
                        parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if block.get('type') == 'text':
                            text = block.get('text', '')
                            if text:
                                parts.append(text)
    except OSError as e:
        logger.warning("Cannot read %s: %s", jsonl_path, e)
    return '\n'.join(parts)


class SearchIndex:
    def __init__(self, db_path: Path | None = None):
        self._db_path = Path(db_path or DB_PATH)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ready = threading.Event()
        self._building = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS indexed_files (
                    session_id   TEXT PRIMARY KEY,
                    mtime        REAL NOT NULL,
                    project_path TEXT NOT NULL,
                    fts_rowid    INTEGER NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
                    session_id   UNINDEXED,
                    project_path UNINDEXED,
                    text,
                    tokenize = 'unicode61'
                );
            """)

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set()

    def build_async(
        self,
        sessions,
        on_progress: Callable[[int, int], None] | None = None,
        on_ready: Callable[[], None] | None = None,
    ) -> None:
        if not self._building.acquire(blocking=False):
            logger.debug("Index build already running, skipping")
            return
        t = threading.Thread(
            target=self._build,
            args=(sessions, on_progress, on_ready),
            daemon=True,
        )
        t.start()

    def _build(self, sessions, on_progress, on_ready) -> None:
        try:
            self._build_inner(sessions, on_progress)
        except Exception as e:
            logger.exception("Index build error: %s", e)
        finally:
            self._building.release()
        self._ready.set()
        if on_ready:
            on_ready()

    def _build_inner(self, sessions, on_progress) -> None:
        def _size(s):
            try:
                return s.jsonl_path.stat().st_size
            except OSError:
                return 0

        sessions = sorted(sessions, key=_size)
        total = len(sessions)
        live_sids = {s.session_id for s in sessions}
        conn = self._connect()
        try:
            indexed = {
                row[0]: row[1]
                for row in conn.execute("SELECT session_id, mtime FROM indexed_files")
            }

            # Prune rows for sessions no longer on disk
            stale = [sid for sid in indexed if sid not in live_sids]
            if stale:
                for sid in stale:
                    old = conn.execute(
                        "SELECT fts_rowid FROM indexed_files WHERE session_id=?", (sid,)
                    ).fetchone()
                    if old:
                        conn.execute("DELETE FROM sessions_fts WHERE rowid=?", (old[0],))
                    conn.execute("DELETE FROM indexed_files WHERE session_id=?", (sid,))
                conn.commit()

            done = 0
            for session in sessions:
                try:
                    mtime = session.jsonl_path.stat().st_mtime
                except OSError:
                    done += 1
                    continue

                sid = session.session_id
                if sid in indexed and abs(indexed[sid] - mtime) < 0.001:
                    done += 1
                    if on_progress and done % 10 == 0:
                        on_progress(done, total)
                    continue

                text = _extract_text(session.jsonl_path)

                conn.execute("BEGIN IMMEDIATE")
                old = conn.execute(
                    "SELECT fts_rowid FROM indexed_files WHERE session_id=?", (sid,)
                ).fetchone()
                if old:
                    conn.execute("DELETE FROM sessions_fts WHERE rowid=?", (old[0],))
                    conn.execute("DELETE FROM indexed_files WHERE session_id=?", (sid,))

                conn.execute(
                    "INSERT INTO sessions_fts(session_id, project_path, text) VALUES(?,?,?)",
                    (sid, session.project_path, text),
                )
                fts_rowid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                conn.execute(
                    "INSERT INTO indexed_files(session_id, mtime, project_path, fts_rowid)"
                    " VALUES(?,?,?,?)",
                    (sid, mtime, session.project_path, fts_rowid),
                )
                conn.execute("COMMIT")
                done += 1
                if on_progress and (done % 10 == 0 or done == total):
                    on_progress(done, total)
        finally:
            conn.close()

    def search(self, query: str) -> list[str]:
        """Return session_ids matching query using FTS5 prefix search."""
        if not query.strip():
            return []
        # Quote each word and add prefix wildcard — safe against special chars
        fts_query = ' '.join(
            f'"{w.replace(chr(34), "")}"*'
            for w in query.split() if w
        )
        if not fts_query:
            return []
        try:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT session_id FROM sessions_fts"
                    " WHERE sessions_fts MATCH ? LIMIT 500",
                    (fts_query,),
                ).fetchall()
                return [r[0] for r in rows]
            except sqlite3.OperationalError as e:
                logger.debug("FTS search error for %r: %s", query, e)
                return []
            finally:
                conn.close()
        except Exception as e:
            logger.exception("Search error: %s", e)
            return []
