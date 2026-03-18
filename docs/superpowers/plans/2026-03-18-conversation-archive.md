# Conversation Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn ClaudeDossier from a conversation viewer into a canonical archive — an append-only mirror that preserves conversations even after source platforms delete them.

**Architecture:** A new `archive_sync.py` module handles safe copying of text files (tail-safe JSONL, atomic rename) and SQLite databases (`sqlite3.backup()` API) from source directories into `~/.local/share/claude-dossier/archive/`. Scanners are updated to read from the archive with fallback to source. Sync runs on startup and refresh in a background thread with a single-writer flock.

**Tech Stack:** Python 3.10+, SQLite3 (stdlib), fcntl (flock), hashlib (SHA-256), pathlib, threading, pytest

**Spec:** `docs/superpowers/specs/2026-03-18-conversation-archive-design.md`

---

## File Structure

| File | Responsibility | Task |
|------|---------------|------|
| `hub/data/archive_sync.py` | **CREATE** — Sync engine: text file copy, SQLite backup, rotation detection, sync log, flock | 1, 2 |
| `hub/data/session_scanner.py` | **MODIFY** — Add `source_path`/`archive_path` to SessionInfo, archive path resolution in scanners | 3 |
| `hub/data/session_parser.py` | **MODIFY** — Fix hardcoded brain path in AntiGravityParser | 4 |
| `hub/main_window.py` | **MODIFY** — Call sync on startup/refresh, background thread, progress | 5 |
| `tests/test_archive_sync.py` | **CREATE** — Unit tests for sync engine | 1, 2 |
| `tests/test_scanner_archive.py` | **CREATE** — Tests for scanner archive path resolution | 3 |

---

### Task 1: Archive Sync Engine — Text Files

**Context:** The core sync logic for JSONL, JSON, and Markdown files. Covers: atomic copy, tail-safe truncation, append detection via SHA-256 prefix hash, rotation detection, sync log, and single-writer flock. This is the foundation everything else builds on.

**Files:**
- Create: `hub/data/archive_sync.py`
- Create: `tests/test_archive_sync.py`

- [ ] **Step 1: Write failing tests for text file sync**

Create `tests/test_archive_sync.py`:

```python
import json
import hashlib
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
    # Old file preserved with rotation suffix
    rotated = [f for f in archive.iterdir() if "pre-rotation" in f.name]
    assert len(rotated) == 1
    assert '{"old":"data"}' in rotated[0].read_text()
    # New content is the primary file
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
    # source has no orphan.jsonl

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
    # Simulate a file being written mid-line
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `GSETTINGS_BACKEND=memory pytest tests/test_archive_sync.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `hub/data/archive_sync.py` — text file sync**

```python
"""Archive sync engine — append-only mirror of conversation sources."""
from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_ARCHIVE_ROOT = Path.home() / ".local" / "share" / "claude-dossier"
_HASH_BLOCK = 4096  # bytes to hash for prefix comparison


def _sha256_prefix(path: Path, size: int = _HASH_BLOCK) -> str:
    """SHA-256 of the first `size` bytes of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(size))
    return h.hexdigest()


def _atomic_copy(src: Path, dst: Path) -> None:
    """Copy src to dst atomically via temp file + rename."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dst.parent, suffix=".tmp")
    try:
        with open(fd, "wb") as out, open(src, "rb") as inp:
            shutil.copyfileobj(inp, out)
        os.rename(tmp, dst)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _tail_safe_copy(src: Path, dst: Path) -> int:
    """Copy src to dst, truncating at last complete newline. Returns bytes written."""
    data = src.read_bytes()
    # Truncate at last newline
    last_nl = data.rfind(b"\n")
    if last_nl == -1:
        return 0  # no complete line
    data = data[: last_nl + 1]
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dst.parent, suffix=".tmp")
    try:
        with open(fd, "wb") as out:
            out.write(data)
        os.rename(tmp, dst)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return len(data)


def _tail_safe_append(src: Path, dst: Path, offset: int) -> int:
    """Append content from src starting at offset, truncate at last newline."""
    with open(src, "rb") as f:
        f.seek(offset)
        new_data = f.read()
    if not new_data:
        return 0
    last_nl = new_data.rfind(b"\n")
    if last_nl == -1:
        return 0
    new_data = new_data[: last_nl + 1]
    with open(dst, "ab") as out:
        out.write(new_data)
    return len(new_data)


def sync_text_files(
    source_root: Path,
    archive_root: Path,
    extensions: set[str] | None = None,
) -> list[dict]:
    """Sync text files from source to archive. Returns list of action dicts."""
    if extensions is None:
        extensions = {".jsonl", ".json", ".md"}

    actions: list[dict] = []
    now = datetime.now(tz=timezone.utc).isoformat()

    if not source_root.exists():
        return actions

    for src_file in source_root.rglob("*"):
        if not src_file.is_file():
            continue
        if src_file.suffix not in extensions:
            continue

        rel = src_file.relative_to(source_root)
        dst_file = archive_root / rel

        if not dst_file.exists():
            # New file — tail-safe copy
            nbytes = _tail_safe_copy(src_file, dst_file)
            actions.append({
                "ts": now, "action": "copy",
                "source": str(src_file), "dest": str(dst_file),
                "bytes": nbytes,
                "sha256_4k": _sha256_prefix(dst_file) if dst_file.exists() else "",
            })
        else:
            # Existing file — check prefix hash
            src_hash = _sha256_prefix(src_file)
            dst_hash = _sha256_prefix(dst_file)
            src_size = src_file.stat().st_size
            dst_size = dst_file.stat().st_size

            if src_hash == dst_hash:
                # Same prefix — check if source grew
                if src_size > dst_size:
                    appended = _tail_safe_append(src_file, dst_file, dst_size)
                    if appended > 0:
                        actions.append({
                            "ts": now, "action": "append",
                            "source": str(src_file), "dest": str(dst_file),
                            "bytes": appended,
                        })
                # else: identical or source shrank (source truncated to same prefix — keep mirror)
            else:
                # Different prefix — rotation detected
                ts_suffix = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
                stem = dst_file.stem
                suffix = dst_file.suffix
                rotated_name = f"{stem}.pre-rotation-{ts_suffix}{suffix}"
                rotated_path = dst_file.parent / rotated_name
                os.rename(dst_file, rotated_path)
                nbytes = _tail_safe_copy(src_file, dst_file)
                actions.append({
                    "ts": now, "action": "rotation_detected",
                    "source": str(src_file),
                    "preserved_as": str(rotated_path),
                    "new_bytes": nbytes,
                })

    return actions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `GSETTINGS_BACKEND=memory pytest tests/test_archive_sync.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add hub/data/archive_sync.py tests/test_archive_sync.py
git commit -m "feat(archive): text file sync engine with rotation detection and tail-safe copy"
```

---

### Task 2: Archive Sync Engine — SQLite Backup + Flock + Sync Log

**Context:** Adds SQLite snapshot support via `sqlite3.backup()`, the single-writer flock, the sync log writer, and the top-level `sync_all()` orchestrator that coordinates everything.

**Files:**
- Modify: `hub/data/archive_sync.py`
- Modify: `tests/test_archive_sync.py`

- [ ] **Step 1: Write failing tests for SQLite backup and flock**

Append to `tests/test_archive_sync.py`:

```python
import sqlite3
import threading


def test_sqlite_backup(tmp_path):
    """SQLite backup creates a valid snapshot."""
    from hub.data.archive_sync import backup_sqlite
    # Create a source DB
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

    # Verify integrity and content
    conn = sqlite3.connect(str(dst))
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("SELECT val FROM t WHERE id=1").fetchone()[0] == "hello"
    conn.close()


def test_sqlite_backup_skips_unchanged(tmp_path):
    """SQLite backup skips when mtime hasn't changed."""
    from hub.data.archive_sync import backup_sqlite
    src = tmp_path / "source.sqlite"
    conn = sqlite3.connect(str(src))
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()

    dst = tmp_path / "snapshot.sqlite"
    backup_sqlite(src, dst)
    first_mtime = dst.stat().st_mtime

    # Backup again without changing source
    result = backup_sqlite(src, dst, last_mtime=src.stat().st_mtime)
    assert result is False  # skipped


def test_sqlite_backup_missing_source(tmp_path):
    """Backup returns False for missing source."""
    from hub.data.archive_sync import backup_sqlite
    result = backup_sqlite(tmp_path / "nonexistent.sqlite", tmp_path / "dst.sqlite")
    assert result is False


def test_sync_log_written(tmp_path):
    """sync_all writes a sync.log with action entries."""
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
    """Two syncs cannot run concurrently — second gets blocked/skipped."""
    from hub.data.archive_sync import acquire_sync_lock, release_sync_lock
    lock_path = tmp_path / ".sync.lock"

    lock_fd = acquire_sync_lock(lock_path)
    assert lock_fd is not None

    # Second attempt should fail (non-blocking)
    lock_fd2 = acquire_sync_lock(lock_path, blocking=False)
    assert lock_fd2 is None

    release_sync_lock(lock_fd)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `GSETTINGS_BACKEND=memory pytest tests/test_archive_sync.py -v -k "sqlite or sync_log or flock"`
Expected: FAIL

- [ ] **Step 3: Implement SQLite backup, flock, sync log, and sync_all**

**Add the following functions to the existing `hub/data/archive_sync.py`** (the file created in Task 1). Add `import sqlite3` to the imports at the top of the file alongside the existing `import fcntl`, `import hashlib`, etc.

```python
import sqlite3  # add to existing imports at top of file


def backup_sqlite(src: Path, dst: Path, last_mtime: float | None = None) -> bool:
    """Backup a SQLite database using the backup API. Returns True if backup was performed."""
    if not src.exists():
        return False
    current_mtime = src.stat().st_mtime
    if last_mtime is not None and current_mtime == last_mtime:
        return False  # unchanged

    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dst.parent, suffix=".sqlite.tmp")
    os.close(fd)
    try:
        src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        dst_conn = sqlite3.connect(tmp)
        src_conn.backup(dst_conn)
        src_conn.close()
        # Verify integrity
        check = dst_conn.execute("PRAGMA integrity_check").fetchone()[0]
        dst_conn.close()
        if check != "ok":
            logger.warning("SQLite backup integrity check failed for %s: %s", src, check)
            os.unlink(tmp)
            return False
        os.rename(tmp, dst)
        return True
    except Exception as e:
        logger.warning("SQLite backup failed for %s: %s", src, e)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False


def acquire_sync_lock(lock_path: Path, blocking: bool = True) -> int | None:
    """Acquire an exclusive flock. Returns file descriptor or None if non-blocking and busy."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    try:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        fcntl.flock(fd, flags)
        return fd
    except OSError:
        os.close(fd)
        return None


def release_sync_lock(fd: int) -> None:
    """Release the flock and close the file descriptor."""
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    except OSError:
        pass


def _write_sync_log(log_path: Path, actions: list[dict]) -> None:
    """Append action entries to the sync log."""
    if not actions:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        for a in actions:
            f.write(json.dumps(a) + "\n")


def _read_last_sqlite_mtimes(log_path: Path) -> dict[str, float]:
    """Read last recorded source_mtime for each sqlite_backup action from sync.log."""
    mtimes: dict[str, float] = {}
    if not log_path.exists():
        return mtimes
    try:
        for line in log_path.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("action") == "sqlite_backup" and entry.get("source_mtime"):
                mtimes[entry["source"]] = entry["source_mtime"]
    except Exception:
        pass  # corrupt log — re-backup everything
    return mtimes


# Source path configuration
_CLAUDE_SOURCE = Path.home() / ".claude" / "projects"
_CODEX_SESSIONS_SOURCE = Path.home() / ".codex" / "sessions"
_CODEX_SQLITE_SOURCE = Path.home() / ".codex" / "state_5.sqlite"
_AG_BRAIN_SOURCE = Path.home() / ".gemini" / "antigravity" / "brain"
_AG_VSCDB_SOURCE = Path.home() / ".config" / "Antigravity" / "User" / "globalStorage" / "state.vscdb"


def sync_all(
    archive_root: Path | None = None,
    claude_source: Path | None = None,
    codex_sessions_source: Path | None = None,
    codex_sqlite_source: Path | None = None,
    ag_brain_source: Path | None = None,
    ag_vscdb_source: Path | None = None,
    on_progress: callable | None = None,
) -> list[dict]:
    """Run a full sync cycle. Returns all actions taken."""
    root = archive_root or DEFAULT_ARCHIVE_ROOT
    archive = root / "archive"
    snapshots = root / "snapshots"
    all_actions: list[dict] = []
    now = datetime.now(tz=timezone.utc).isoformat()

    # Text file syncs
    sources = [
        (claude_source or _CLAUDE_SOURCE, archive / "claude" / "projects", {".jsonl", ".json"}),
        (codex_sessions_source or _CODEX_SESSIONS_SOURCE, archive / "codex" / "sessions", {".jsonl"}),
        (ag_brain_source or _AG_BRAIN_SOURCE, archive / "antigravity" / "brain", {".md", ".json"}),
    ]
    for src, dst, exts in sources:
        actions = sync_text_files(src, dst, extensions=exts)
        all_actions.extend(actions)
        if on_progress:
            on_progress(len(all_actions), -1)

    # SQLite snapshots
    # SQLite snapshots — retrieve last_mtime from sync.log to avoid re-backup on every restart
    last_mtimes = _read_last_sqlite_mtimes(root / "sync.log")

    sqlite_sources = [
        (codex_sqlite_source or _CODEX_SQLITE_SOURCE, snapshots / "codex_state_5.sqlite"),
        (ag_vscdb_source or _AG_VSCDB_SOURCE, snapshots / "antigravity_state.vscdb"),
    ]
    for src, dst in sqlite_sources:
        last_mt = last_mtimes.get(str(src))
        if backup_sqlite(src, dst, last_mtime=last_mt):
            # Record source mtime so next restart can skip if unchanged
            src_mt = src.stat().st_mtime if src.exists() else None
            all_actions.append({"ts": now, "action": "sqlite_backup", "source": str(src), "dest": str(dst), "source_mtime": src_mt})
        else:
            all_actions.append({"ts": now, "action": "skip", "source": str(src), "reason": "unchanged_or_missing"})

    # Write sync log
    _write_sync_log(root / "sync.log", all_actions)

    return all_actions
```

- [ ] **Step 4: Run all tests**

Run: `GSETTINGS_BACKEND=memory pytest tests/test_archive_sync.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add hub/data/archive_sync.py tests/test_archive_sync.py
git commit -m "feat(archive): SQLite backup, flock, sync log, and sync_all orchestrator"
```

---

### Task 3: Scanner Archive Path Resolution

**Context:** Add `source_path` and `archive_path` fields to `SessionInfo`. Update all three scanners to resolve `jsonl_path` to archive when available, falling back to source. Update `SessionScanner` to accept `archive_root`.

**Files:**
- Modify: `hub/data/session_scanner.py:18-29` (SessionInfo), `111-155` (ClaudeScanner), `157-277` (CodexScanner), `280-335` (AntiGravityScanner), `338-359` (SessionScanner)
- Create: `tests/test_scanner_archive.py`

- [ ] **Step 1: Write failing tests for archive path resolution**

Create `tests/test_scanner_archive.py`:

```python
import json
from pathlib import Path
from datetime import datetime, timezone


def test_claude_scanner_prefers_archive(tmp_path):
    """ClaudeScanner reads from archive when files exist there."""
    from hub.data.session_scanner import ClaudeScanner

    # Set up source with index
    source = tmp_path / "source" / "-home-user-proj"
    source.mkdir(parents=True)
    (source / "sessions-index.json").write_text(json.dumps({
        "version": 1, "originalPath": "/home/user/proj", "entries": []
    }))
    (source / "abc.jsonl").write_text('{"type":"user","message":{"content":"hello"},"uuid":"u1","timestamp":"2026-01-01T00:00:00Z"}\n')

    # Set up archive with the same file
    archive = tmp_path / "archive" / "claude" / "projects" / "-home-user-proj"
    archive.mkdir(parents=True)
    (archive / "sessions-index.json").write_text(json.dumps({
        "version": 1, "originalPath": "/home/user/proj", "entries": []
    }))
    (archive / "abc.jsonl").write_text('{"type":"user","message":{"content":"hello"},"uuid":"u1","timestamp":"2026-01-01T00:00:00Z"}\n')

    scanner = ClaudeScanner(
        projects_root=source.parent,
        archive_projects_root=archive.parent,
    )
    projects = scanner.scan()
    sessions = [s for p in projects for s in p.sessions]
    assert len(sessions) == 1
    assert sessions[0].jsonl_path == archive / "abc.jsonl"  # reads from archive
    assert sessions[0].source_path == source / "abc.jsonl"  # source preserved


def test_claude_scanner_falls_back_to_source(tmp_path):
    """When archive doesn't exist, scanner reads from source as before."""
    from hub.data.session_scanner import ClaudeScanner

    source = tmp_path / "source" / "-home-user-proj"
    source.mkdir(parents=True)
    (source / "sessions-index.json").write_text(json.dumps({
        "version": 1, "originalPath": "/home/user/proj", "entries": []
    }))
    (source / "abc.jsonl").write_text('{"type":"user","message":{"content":"hi"},"uuid":"u1","timestamp":"2026-01-01T00:00:00Z"}\n')

    scanner = ClaudeScanner(
        projects_root=source.parent,
        archive_projects_root=tmp_path / "no_archive",  # doesn't exist
    )
    projects = scanner.scan()
    sessions = [s for p in projects for s in p.sessions]
    assert len(sessions) == 1
    assert sessions[0].jsonl_path == source / "abc.jsonl"
    assert sessions[0].source_path == source / "abc.jsonl"
    assert sessions[0].archive_path is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `GSETTINGS_BACKEND=memory pytest tests/test_scanner_archive.py -v`
Expected: FAIL

- [ ] **Step 3: Add `source_path` and `archive_path` to SessionInfo**

Modify `hub/data/session_scanner.py:18-29` — add two optional fields after `agent_source`:

```python
@dataclass
class SessionInfo:
    session_id: str
    first_prompt: str
    message_count: int
    created: datetime
    modified: datetime
    git_branch: str
    project_path: str
    is_sidechain: bool
    jsonl_path: Path
    agent_source: str = "claude"
    source_path: Path | None = None
    archive_path: Path | None = None
```

- [ ] **Step 4: Update ClaudeScanner to accept `archive_projects_root`**

Add `archive_projects_root` parameter to `ClaudeScanner.__init__`. After each `SessionInfo` is created (both from index entries and orphan discovery), resolve the archive path:

```python
class ClaudeScanner:
    def __init__(self, projects_root: Path | None = None, archive_projects_root: Path | None = None):
        self.projects_root = projects_root or DEFAULT_PROJECTS_ROOT
        self.archive_root = archive_projects_root
```

For each session, after `info` is created, add path resolution:

```python
# After creating SessionInfo (both indexed and orphan paths):
info.source_path = info.jsonl_path
if self.archive_root:
    # Compute archive equivalent
    rel = info.jsonl_path.relative_to(self.projects_root)
    archive_file = self.archive_root / rel
    if archive_file.exists():
        info.archive_path = archive_file
        info.jsonl_path = archive_file
```

- [ ] **Step 4b: Add mirror-only detection**

Sessions where `source_path` doesn't exist but `archive_path` does are "mirror-only" — the source was deleted. Add a property or flag to `SessionInfo`:

```python
@property
def is_mirror_only(self) -> bool:
    """True if this session only exists in the archive, not the source."""
    return self.archive_path is not None and (self.source_path is None or not self.source_path.exists())
```

Note: This is a `@property`, not a stored field — it evaluates at access time since source files may appear/disappear between scans.

- [ ] **Step 5: Update CodexScanner and AntiGravityScanner similarly**

Apply the same pattern: accept an archive path parameter, resolve `jsonl_path` to archive when available. For `AntiGravityScanner`, brain directories in archive map to `archive/antigravity/brain/{conv_id}/`.

- [ ] **Step 6: Update SessionScanner to pass archive paths through**

```python
class SessionScanner:
    def __init__(self, projects_root=None, codex_root=None, antigravity_root=None,
                 codex_sqlite_path=None, antigravity_brain_root=None,
                 archive_root: Path | None = None):
        ar = archive_root or Path.home() / ".local" / "share" / "claude-dossier"
        self.claude = ClaudeScanner(
            projects_root,
            archive_projects_root=ar / "archive" / "claude" / "projects",
        )
        # ... similar for codex and antigravity ...
```

When `projects_root` is set (test mode), also fake the archive root to prevent reading real archive.

- [ ] **Step 7: Run all tests**

Run: `GSETTINGS_BACKEND=memory pytest tests/ -v`
Expected: ALL PASS (new + existing)

- [ ] **Step 8: Commit**

```bash
git add hub/data/session_scanner.py tests/test_scanner_archive.py
git commit -m "feat(archive): scanner archive path resolution with source/archive provenance"
```

---

### Task 4: AntiGravityParser Brain Path Fix

**Context:** `AntiGravityParser.parse()` at line 275 hardcodes `Path.home() / ".gemini" / "antigravity" / "brain" / conv_id` when checking for brain content alongside .pb sessions. This bypasses the archive. Fix: check archive brain path first, fall back to source.

**Files:**
- Modify: `hub/data/session_parser.py:273-285`
- Modify: `tests/test_antigravity_brain.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_antigravity_brain.py`:

```python
def test_parser_uses_archive_brain_path(tmp_path):
    """AntiGravityParser checks archive brain path, not just hardcoded source."""
    from hub.data.session_parser import AntiGravityParser, ParsedMessage

    # Create a fake .pb file (parser will use vscdb path which won't match)
    pb = tmp_path / "conv-123.pb"
    pb.write_bytes(b"\x00" * 10)

    # Create brain content in an archive-like location
    brain = tmp_path / "brain" / "conv-123"
    brain.mkdir(parents=True)
    (brain / "task.md").write_text("# Archived task\nThis is from the archive.")

    parser = AntiGravityParser()
    # Pass archive_brain_root so parser knows where to look
    msgs = parser.parse(pb, archive_brain_root=tmp_path / "brain")

    brain_msgs = [m for m in msgs if "Archived task" in m.text]
    assert len(brain_msgs) == 1
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Modify AntiGravityParser.parse() to accept `archive_brain_root`**

At `hub/data/session_parser.py`, modify the `parse()` method signature and the brain lookup block (lines 273-285):

```python
def parse(self, path: Path, archive_brain_root: Path | None = None) -> list[ParsedMessage]:
    # ... existing code ...

    # After the vscdb try/except block, replace the hardcoded brain lookup:
    from hub.data.antigravity_brain import load_brain
    brain_dir = None
    # Check archive brain path first
    if archive_brain_root:
        candidate = archive_brain_root / conv_id
        if candidate.is_dir():
            brain_dir = candidate
    # Fall back to source brain path
    if brain_dir is None:
        candidate = Path.home() / ".gemini" / "antigravity" / "brain" / conv_id
        if candidate.is_dir():
            brain_dir = candidate

    if brain_dir:
        brain = load_brain(brain_dir)
        for key, label in [("task", "Task"), ("implementation_plan", "Plan"), ("walkthrough", "Walkthrough")]:
            text = brain.get(key, "")
            if text.strip():
                results.append(ParsedMessage(
                    type=MessageType.ASSISTANT,
                    text=f"**{label}**\n\n{text}",
                    timestamp=None, uuid=conv_id,
                ))
```

**Also update `SessionParser` to pass through `archive_brain_root`:**

```python
class SessionParser:
    def __init__(self, agent_source: str = "claude", include_progress: bool = False,
                 include_snapshots: bool = False, archive_brain_root: Path | None = None):
        self.agent_source = agent_source
        self.archive_brain_root = archive_brain_root
        if agent_source == "codex":
            self.delegate = CodexParser(include_progress, include_snapshots)
        elif agent_source == "antigravity":
            self.delegate = AntiGravityParser(include_progress, include_snapshots)
        else:
            self.delegate = ClaudeParser(include_progress, include_snapshots)

    def parse(self, path: Path) -> list[ParsedMessage]:
        if self.agent_source == "antigravity":
            return self.delegate.parse(path, archive_brain_root=self.archive_brain_root)
        return self.delegate.parse(path)
```

The callers that create `SessionParser` (search_index.py, session_viewer.py) need to pass `archive_brain_root` when constructing for antigravity sessions. Since the archive root is available from the `SessionScanner`, the simplest approach is to store it on the `SessionInfo` or derive it from `archive_path`.

- [ ] **Step 4: Run all tests**

Run: `GSETTINGS_BACKEND=memory pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add hub/data/session_parser.py tests/test_antigravity_brain.py
git commit -m "fix(parser): use archive brain path before hardcoded source in AntiGravityParser"
```

---

### Task 5: Startup/Refresh Sync Integration

**Context:** Wire `sync_all()` into the app lifecycle. On startup, sync runs in a background thread before scanners populate the UI. On refresh, sync runs again. Uses the single-writer flock. Shows progress via toast notifications.

**Files:**
- Modify: `hub/main_window.py:30-58` (startup), `120-` (refresh)

- [ ] **Step 1: Modify `_load_data` to sync before scanning**

Replace the current `_load_data` in `hub/main_window.py`:

```python
def _load_data(self):
    import traceback
    import threading
    try:
        from hub.data.archive_sync import sync_all, acquire_sync_lock, release_sync_lock, DEFAULT_ARCHIVE_ROOT

        lock_path = DEFAULT_ARCHIVE_ROOT / ".sync.lock"
        lock_fd = acquire_sync_lock(lock_path, blocking=False)

        if lock_fd is not None:
            # We got the lock — sync in background, then scan
            def do_sync():
                try:
                    sync_all(on_progress=lambda done, total: None)  # TODO: wire progress toast
                except Exception:
                    traceback.print_exc()
                finally:
                    release_sync_lock(lock_fd)
                    GLib.idle_add(self._scan_and_setup)  # MUST be in finally — UI populates even if sync fails

            threading.Thread(target=do_sync, daemon=True).start()
        else:
            # Lock busy — skip sync, scan existing archive
            self._scan_and_setup()
    except Exception:
        traceback.print_exc()
    return GLib.SOURCE_REMOVE


def _scan_and_setup(self):
    import traceback
    try:
        from hub.settings import Settings
        settings = Settings.new()
        enable_claude = settings.get_boolean("enable-claude")
        enable_codex = settings.get_boolean("enable-codex")
        enable_ag = settings.get_boolean("enable-antigravity")

        from hub.data.session_scanner import SessionScanner
        from hub.data.tree_builder import TreeBuilder
        scanner = SessionScanner()

        projects = []
        if enable_claude:
            projects.extend(scanner.claude.scan())
        if enable_codex:
            projects.extend(scanner.codex.scan())
        if enable_ag:
            projects.extend(scanner.antigravity.scan())
        self._projects = projects

        self._tree_root = TreeBuilder().build(self._projects)
        self._setup_ui()
    except Exception:
        traceback.print_exc()
```

- [ ] **Step 2: Update `_on_refresh_requested` similarly**

Add sync before re-scan in the refresh handler, using the same lock-then-scan pattern.

- [ ] **Step 3: Manual smoke test**

Run: `./run-dev.sh`
Verify:
- App starts and shows conversations (sync runs first, then UI populates)
- `~/.local/share/claude-dossier/archive/` is created with mirrored files
- `~/.local/share/claude-dossier/sync.log` has entries
- Refresh button triggers a new sync cycle
- Second app window skips sync (lock busy)

- [ ] **Step 4: Commit**

```bash
git add hub/main_window.py
git commit -m "feat(archive): sync on startup and refresh with background thread and flock"
```

---

### Task 6: Integration Smoke Test

- [ ] **Step 1: Run full test suite**

Run: `GSETTINGS_BACKEND=memory pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: Verify archive contents**

```bash
# Check archive was created
ls ~/.local/share/claude-dossier/archive/

# Check sync log
tail -5 ~/.local/share/claude-dossier/sync.log

# Check JSONL files end with newline
find ~/.local/share/claude-dossier/archive -name '*.jsonl' | head -5 | while read f; do
  test "$(tail -c1 "$f")" = "" && echo "OK: $f" || echo "BAD: $f"
done

# Check SQLite snapshot integrity (if exists)
sqlite3 ~/.local/share/claude-dossier/snapshots/codex_state_5.sqlite "PRAGMA integrity_check;" 2>/dev/null || echo "No codex snapshot yet"

# Check disk usage
du -sh ~/.local/share/claude-dossier/
```

- [ ] **Step 3: Simulate rotation and verify preservation**

```bash
# Find a small JSONL in the archive
FIRST=$(find ~/.local/share/claude-dossier/archive -name '*.jsonl' -size +1k | head -1)
echo "Testing rotation on: $FIRST"
wc -l "$FIRST"
# Note the line count — after next sync with a rotated source, both versions should exist
```

- [ ] **Step 4: Final commit if adjustments needed**

```bash
git commit -m "fix: integration adjustments from archive smoke testing"
```
