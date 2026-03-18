import sqlite3
from pathlib import Path


def _make_db(tmp_path, threads):
    """Create a minimal state_5.sqlite with threads table."""
    db = tmp_path / "state_5.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("""CREATE TABLE threads (
        id TEXT PRIMARY KEY,
        rollout_path TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        source TEXT NOT NULL DEFAULT 'cli',
        model_provider TEXT NOT NULL DEFAULT 'openai',
        cwd TEXT NOT NULL,
        title TEXT NOT NULL,
        sandbox_policy TEXT NOT NULL DEFAULT 'locked',
        approval_mode TEXT NOT NULL DEFAULT 'suggest',
        tokens_used INTEGER NOT NULL DEFAULT 0,
        has_user_event INTEGER NOT NULL DEFAULT 0,
        archived INTEGER NOT NULL DEFAULT 0,
        archived_at INTEGER,
        git_sha TEXT,
        git_branch TEXT,
        git_origin_url TEXT,
        cli_version TEXT NOT NULL DEFAULT '',
        first_user_message TEXT NOT NULL DEFAULT '',
        agent_nickname TEXT,
        agent_role TEXT,
        memory_mode TEXT NOT NULL DEFAULT 'enabled'
    )""")
    for t in threads:
        conn.execute(
            "INSERT INTO threads (id, rollout_path, created_at, updated_at, cwd, title, git_branch, first_user_message, archived) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (t["id"], t.get("rollout_path", ""), t["created_at"], t["updated_at"],
             t["cwd"], t["title"], t.get("git_branch", ""), t.get("first_user_message", ""), t.get("archived", 0)),
        )
    conn.commit()
    conn.close()
    return db


def test_loads_non_archived_threads(tmp_path):
    from hub.data.codex_sqlite import load_codex_threads
    _make_db(tmp_path, [
        {"id": "t1", "created_at": 1710000000, "updated_at": 1710000100,
         "cwd": "/home/user/project", "title": "Fix bug", "git_branch": "main",
         "first_user_message": "fix the login bug"},
        {"id": "t2", "created_at": 1710000200, "updated_at": 1710000300,
         "cwd": "/home/user/project", "title": "Archived", "archived": 1},
    ])
    threads = load_codex_threads(tmp_path / "state_5.sqlite")
    assert len(threads) == 1
    assert threads[0]["id"] == "t1"
    assert threads[0]["title"] == "Fix bug"
    assert threads[0]["git_branch"] == "main"
    assert threads[0]["first_user_message"] == "fix the login bug"


def test_returns_empty_for_missing_db(tmp_path):
    from hub.data.codex_sqlite import load_codex_threads
    assert load_codex_threads(tmp_path / "nonexistent.sqlite") == []


def test_groups_by_cwd(tmp_path):
    from hub.data.codex_sqlite import load_codex_threads
    _make_db(tmp_path, [
        {"id": "t1", "created_at": 1710000000, "updated_at": 1710000100,
         "cwd": "/proj/a", "title": "Task A"},
        {"id": "t2", "created_at": 1710000200, "updated_at": 1710000300,
         "cwd": "/proj/b", "title": "Task B"},
    ])
    threads = load_codex_threads(tmp_path / "state_5.sqlite")
    cwds = {t["cwd"] for t in threads}
    assert cwds == {"/proj/a", "/proj/b"}
