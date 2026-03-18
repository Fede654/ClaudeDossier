import json
import sqlite3
from pathlib import Path


def test_codex_scanner_includes_sqlite_threads(tmp_path):
    from hub.data.session_scanner import CodexScanner

    # Create sessions dir with one JSONL
    sessions_dir = tmp_path / "sessions" / "2026" / "03" / "18"
    sessions_dir.mkdir(parents=True)
    jsonl = sessions_dir / "rollout-abc.jsonl"
    jsonl.write_text(json.dumps({
        "type": "response_item",
        "payload": {"type": "message", "role": "user",
                    "content": [{"type": "input_text", "text": "<cwd>/proj</cwd>\nhello"}]}
    }))

    # Create SQLite with a thread that has NO matching JSONL
    db = tmp_path / "state_5.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("""CREATE TABLE threads (
        id TEXT PRIMARY KEY, rollout_path TEXT NOT NULL,
        created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
        source TEXT NOT NULL DEFAULT 'cli', model_provider TEXT NOT NULL DEFAULT 'openai',
        cwd TEXT NOT NULL, title TEXT NOT NULL,
        sandbox_policy TEXT NOT NULL DEFAULT 'locked', approval_mode TEXT NOT NULL DEFAULT 'suggest',
        tokens_used INTEGER NOT NULL DEFAULT 0, has_user_event INTEGER NOT NULL DEFAULT 0,
        archived INTEGER NOT NULL DEFAULT 0, archived_at INTEGER,
        git_sha TEXT, git_branch TEXT, git_origin_url TEXT,
        cli_version TEXT NOT NULL DEFAULT '', first_user_message TEXT NOT NULL DEFAULT '',
        agent_nickname TEXT, agent_role TEXT, memory_mode TEXT NOT NULL DEFAULT 'enabled'
    )""")
    conn.execute(
        "INSERT INTO threads (id, rollout_path, created_at, updated_at, cwd, title, git_branch, first_user_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("sqlite-only-thread", "", 1710000000, 1710000100, "/proj/sqlite", "SQLite Thread", "feat/x", "do the thing"),
    )
    conn.commit()
    conn.close()

    scanner = CodexScanner(codex_root=tmp_path / "sessions", sqlite_path=db)
    projects = scanner.scan()

    all_sessions = [s for p in projects for s in p.sessions]
    ids = {s.session_id for s in all_sessions}
    assert "sqlite-only-thread" in ids

    sqlite_session = next(s for s in all_sessions if s.session_id == "sqlite-only-thread")
    assert sqlite_session.first_prompt == "do the thing"
    assert sqlite_session.git_branch == "feat/x"
