"""Archive sync engine — append-only mirror of conversation sources."""
from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_ARCHIVE_ROOT = Path.home() / ".local" / "share" / "claude-dossier"
_HASH_BLOCK = 4096


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
    last_nl = data.rfind(b"\n")
    if last_nl == -1:
        return 0
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
            nbytes = _tail_safe_copy(src_file, dst_file)
            actions.append({
                "ts": now, "action": "copy",
                "source": str(src_file), "dest": str(dst_file),
                "bytes": nbytes,
                "sha256_4k": _sha256_prefix(dst_file) if dst_file.exists() else "",
            })
        else:
            src_size = src_file.stat().st_size
            dst_size = dst_file.stat().st_size

            # Compare only the bytes present in the archive (up to _HASH_BLOCK).
            # This detects rotation (diverged prefix) vs append (same prefix, source grew).
            prefix_size = min(dst_size, _HASH_BLOCK)
            src_prefix_hash = _sha256_prefix(src_file, size=prefix_size)
            dst_prefix_hash = _sha256_prefix(dst_file, size=prefix_size)

            if src_prefix_hash == dst_prefix_hash:
                if src_size > dst_size:
                    appended = _tail_safe_append(src_file, dst_file, dst_size)
                    if appended > 0:
                        actions.append({
                            "ts": now, "action": "append",
                            "source": str(src_file), "dest": str(dst_file),
                            "bytes": appended,
                        })
            else:
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


def backup_sqlite(src: Path, dst: Path, last_mtime: float | None = None) -> bool:
    """Backup a SQLite database using the backup API. Returns True if backup was performed."""
    if not src.exists():
        return False
    current_mtime = src.stat().st_mtime
    if last_mtime is not None and current_mtime == last_mtime:
        return False

    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dst.parent, suffix=".sqlite.tmp")
    os.close(fd)
    try:
        src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        dst_conn = sqlite3.connect(tmp)
        src_conn.backup(dst_conn)
        src_conn.close()
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
        pass
    return mtimes


# Source path defaults
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

    # SQLite snapshots with mtime persistence
    last_mtimes = _read_last_sqlite_mtimes(root / "sync.log")
    sqlite_sources = [
        (codex_sqlite_source or _CODEX_SQLITE_SOURCE, snapshots / "codex_state_5.sqlite"),
        (ag_vscdb_source or _AG_VSCDB_SOURCE, snapshots / "antigravity_state.vscdb"),
    ]
    for src, dst in sqlite_sources:
        last_mt = last_mtimes.get(str(src))
        if backup_sqlite(src, dst, last_mtime=last_mt):
            src_mt = src.stat().st_mtime if src.exists() else None
            all_actions.append({"ts": now, "action": "sqlite_backup", "source": str(src), "dest": str(dst), "source_mtime": src_mt})
        else:
            all_actions.append({"ts": now, "action": "skip", "source": str(src), "reason": "unchanged_or_missing"})

    # Write sync log
    _write_sync_log(root / "sync.log", all_actions)

    return all_actions
