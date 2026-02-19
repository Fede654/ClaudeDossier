"""Tests for SearchIndex FTS5 full-text search."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from hub.data.search_index import SearchIndex, _extract_text
from hub.data.session_scanner import SessionInfo


def _make_jsonl(path: Path, messages: list[tuple[str, str]]) -> None:
    """Write a JSONL file with (role, text) pairs."""
    lines = [
        json.dumps({"type": role, "message": {"content": text}, "timestamp": "2024-01-01T00:00:00Z"})
        for role, text in messages
    ]
    path.write_text('\n'.join(lines))


def _make_session(tmp_path: Path, sid: str, messages: list[tuple[str, str]]) -> SessionInfo:
    jsonl = tmp_path / f"{sid}.jsonl"
    _make_jsonl(jsonl, messages)
    return SessionInfo(
        session_id=sid,
        first_prompt=messages[0][1] if messages else '',
        message_count=len(messages),
        created=datetime(2024, 1, 1, tzinfo=timezone.utc),
        modified=datetime(2024, 1, 1, tzinfo=timezone.utc),
        git_branch='main',
        project_path='/tmp/proj',
        is_sidechain=False,
        jsonl_path=jsonl,
    )


def _build_sync(index: SearchIndex, sessions) -> None:
    index._build(sessions, on_progress=None, on_ready=None)


def test_indexes_and_finds_session(tmp_path):
    index = SearchIndex(db_path=tmp_path / "s.db")
    s = _make_session(tmp_path, "s1", [("user", "implement authentication flow")])
    _build_sync(index, [s])
    assert "s1" in index.search("authentication")


def test_no_match_returns_empty(tmp_path):
    index = SearchIndex(db_path=tmp_path / "s.db")
    s = _make_session(tmp_path, "s1", [("user", "hello world")])
    _build_sync(index, [s])
    assert index.search("zzznomatch") == []


def test_prefix_search(tmp_path):
    index = SearchIndex(db_path=tmp_path / "s.db")
    s = _make_session(tmp_path, "s1", [("user", "implementing authentication")])
    _build_sync(index, [s])
    assert "s1" in index.search("authen")


def test_skips_up_to_date_file(tmp_path):
    db = tmp_path / "s.db"
    index = SearchIndex(db_path=db)
    s = _make_session(tmp_path, "s1", [("user", "original text")])
    _build_sync(index, [s])

    # Overwrite file content but preserve mtime — should NOT re-index
    mtime = s.jsonl_path.stat().st_mtime
    s.jsonl_path.write_text('garbage')
    import os; os.utime(s.jsonl_path, (mtime, mtime))

    index2 = SearchIndex(db_path=db)
    _build_sync(index2, [s])
    assert "s1" in index2.search("original")


def test_reindexes_changed_file(tmp_path):
    db = tmp_path / "s.db"
    index = SearchIndex(db_path=db)
    s = _make_session(tmp_path, "s1", [("user", "old content")])
    _build_sync(index, [s])

    time.sleep(0.05)
    s = _make_session(tmp_path, "s1", [("user", "new unique xyzzy content")])
    _build_sync(index, [s])

    assert "s1" in index.search("xyzzy")
    assert index.search("old") == []
