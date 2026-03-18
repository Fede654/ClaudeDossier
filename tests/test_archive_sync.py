import json
import hashlib
import sqlite3
import threading
from pathlib import Path


def test_sync_copies_new_file(tmp_path):
    """New file in source gets copied to archive."""
    from hub.data.archive_sync import sync_text_files
    source = tmp_path / "source"
    archive = tmp_path / "archive"
    source.mkdir()
    archive.mkdir()
    (source / "test.jsonl").write_text('{"type":"user"}\n{"type":"assistant"}\n')

    actions = sync_text_files(source, archive, extensions={".jsonl"})
    assert (archive / "test.jsonl").exists()
    assert (archive / "test.jsonl").read_text() == '{"type":"user"}\n{"type":"assistant"}\n'
    assert any(a["action"] == "copy" for a in actions)


def test_sync_appends_grown_file(tmp_path):
    """Source file grew (same prefix) — append new content to mirror."""
    from hub.data.archive_sync import sync_text_files
    source = tmp_path / "source"
    archive = tmp_path / "archive"
    source.mkdir()
    archive.mkdir()
    original = '{"line":1}\n{"line":2}\n'
    (archive / "test.jsonl").write_text(original)
    (source / "test.jsonl").write_text(original + '{"line":3}\n')

    actions = sync_text_files(source, archive, extensions={".jsonl"})
    content = (archive / "test.jsonl").read_text()
    assert '{"line":3}' in content
    assert content.startswith('{"line":1}')
    assert any(a["action"] == "append" for a in actions)


def test_sync_detects_rotation(tmp_path):
    """Source file has different prefix — rotation detected, both preserved."""
    from hub.data.archive_sync import sync_text_files
    source = tmp_path / "source"
    archive = tmp_path / "archive"
    source.mkdir()
    archive.mkdir()
    (archive / "test.jsonl").write_text('{"old":"data"}\n')
    (source / "test.jsonl").write_text('{"new":"rotated"}\n')

    actions = sync_text_files(source, archive, extensions={".jsonl"})
    rotated = [f for f in archive.iterdir() if "pre-rotation" in f.name]
    assert len(rotated) == 1
    assert '{"old":"data"}' in rotated[0].read_text()
    assert '{"new":"rotated"}' in (archive / "test.jsonl").read_text()
    assert any(a["action"] == "rotation_detected" for a in actions)


def test_sync_preserves_deleted_source(tmp_path):
    """Source file gone — mirror keeps it, no action."""
    from hub.data.archive_sync import sync_text_files
    source = tmp_path / "source"
    archive = tmp_path / "archive"
    source.mkdir()
    archive.mkdir()
    (archive / "orphan.jsonl").write_text('{"preserved":"yes"}\n')

    actions = sync_text_files(source, archive, extensions={".jsonl"})
    assert (archive / "orphan.jsonl").exists()
    assert (archive / "orphan.jsonl").read_text() == '{"preserved":"yes"}\n'


def test_sync_tail_safe_truncation(tmp_path):
    """Partial last line gets truncated to last complete newline."""
    from hub.data.archive_sync import sync_text_files
    source = tmp_path / "source"
    archive = tmp_path / "archive"
    source.mkdir()
    archive.mkdir()
    (source / "test.jsonl").write_text('{"complete":true}\n{"partial":tr')

    actions = sync_text_files(source, archive, extensions={".jsonl"})
    content = (archive / "test.jsonl").read_text()
    assert content == '{"complete":true}\n'
    assert content.endswith("\n")


def test_sync_walks_subdirectories(tmp_path):
    """Sync walks nested directory structure."""
    from hub.data.archive_sync import sync_text_files
    source = tmp_path / "source"
    archive = tmp_path / "archive"
    (source / "sub" / "deep").mkdir(parents=True)
    archive.mkdir()
    (source / "sub" / "deep" / "session.jsonl").write_text('{"ok":true}\n')

    sync_text_files(source, archive, extensions={".jsonl"})
    assert (archive / "sub" / "deep" / "session.jsonl").exists()


def test_sync_respects_extensions_filter(tmp_path):
    """Only files with matching extensions are synced."""
    from hub.data.archive_sync import sync_text_files
    source = tmp_path / "source"
    archive = tmp_path / "archive"
    source.mkdir()
    archive.mkdir()
    (source / "good.jsonl").write_text('{"ok":true}\n')
    (source / "skip.pb").write_bytes(b"\x00" * 100)

    sync_text_files(source, archive, extensions={".jsonl"})
    assert (archive / "good.jsonl").exists()
    assert not (archive / "skip.pb").exists()


def test_sqlite_backup(tmp_path):
    from hub.data.archive_sync import backup_sqlite
    src = tmp_path / "source.sqlite"
    conn = sqlite3.connect(str(src))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    conn.execute("INSERT INTO t VALUES (1, 'hello')")
    conn.commit()
    conn.close()

    dst = tmp_path / "snapshot.sqlite"
    result = backup_sqlite(src, dst)
    assert result is True
    assert dst.exists()

    conn = sqlite3.connect(str(dst))
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("SELECT val FROM t WHERE id=1").fetchone()[0] == "hello"
    conn.close()


def test_sqlite_backup_skips_unchanged(tmp_path):
    from hub.data.archive_sync import backup_sqlite
    src = tmp_path / "source.sqlite"
    conn = sqlite3.connect(str(src))
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()

    dst = tmp_path / "snapshot.sqlite"
    backup_sqlite(src, dst)

    result = backup_sqlite(src, dst, last_mtime=src.stat().st_mtime)
    assert result is False


def test_sqlite_backup_missing_source(tmp_path):
    from hub.data.archive_sync import backup_sqlite
    result = backup_sqlite(tmp_path / "nonexistent.sqlite", tmp_path / "dst.sqlite")
    assert result is False


def test_sync_log_written(tmp_path):
    from hub.data.archive_sync import sync_all
    source_root = tmp_path / "sources"
    archive_root = tmp_path / "dossier"
    claude_src = source_root / "claude"
    claude_src.mkdir(parents=True)
    (claude_src / "test.jsonl").write_text('{"ok":true}\n')

    sync_all(
        archive_root=archive_root,
        claude_source=claude_src,
        codex_sessions_source=source_root / "codex_fake",
        codex_sqlite_source=source_root / "codex_fake.sqlite",
        ag_brain_source=source_root / "ag_fake",
        ag_vscdb_source=source_root / "ag_fake.vscdb",
    )

    log_path = archive_root / "sync.log"
    assert log_path.exists()
    entries = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
    assert len(entries) >= 1
    assert entries[0]["action"] == "copy"


def test_flock_prevents_concurrent_sync(tmp_path):
    from hub.data.archive_sync import acquire_sync_lock, release_sync_lock
    lock_path = tmp_path / ".sync.lock"

    lock_fd = acquire_sync_lock(lock_path)
    assert lock_fd is not None

    lock_fd2 = acquire_sync_lock(lock_path, blocking=False)
    assert lock_fd2 is None

    release_sync_lock(lock_fd)
