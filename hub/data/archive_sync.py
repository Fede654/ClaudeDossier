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
