"""Read/write Claude Code memory files with YAML frontmatter — zero gi imports."""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_INDEX_LINK_RE = re.compile(r"^\s*-\s+\[([^\]]*)\]\(([^)]+)\)", re.MULTILINE)
_SLUG_RE = re.compile(r"[^\w]+")


class MtimeConflictError(Exception):
    """Raised when the file has been externally modified since it was read."""


@dataclass
class MemoryEntry:
    path: Path
    name: str
    description: str
    type: str
    content: str
    mtime: float


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (frontmatter_dict, body) from a memory file's text."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_block = m.group(1)
    body = text[m.end():]
    fm: dict[str, str] = {}
    for line in fm_block.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()
    return fm, body


def _render_frontmatter(entry: MemoryEntry) -> str:
    """Serialise a MemoryEntry back to disk format."""
    fm_lines = [
        "---",
        f"name: {entry.name}",
        f"description: {entry.description}",
        f"type: {entry.type}",
        "---",
        "",
    ]
    body = entry.content if entry.content.endswith("\n") else entry.content + "\n"
    return "\n".join(fm_lines) + "\n" + body


def _read_entry(path: Path) -> MemoryEntry | None:
    """Parse a single memory file into a MemoryEntry, or return None on error."""
    try:
        text = path.read_text(encoding="utf-8")
        mtime = path.stat().st_mtime
    except OSError:
        return None
    fm, body = _parse_frontmatter(text)
    return MemoryEntry(
        path=path,
        name=fm.get("name", path.stem),
        description=fm.get("description", ""),
        type=fm.get("type", ""),
        content=body,
        mtime=mtime,
    )


def read_memory_dir(directory: Path) -> list[MemoryEntry]:
    """Return all memory entries found in *directory*.

    If MEMORY.md exists, entries are read in index order.  Otherwise all
    ``*.md`` files (except MEMORY.md) are returned in lexicographic order.
    Returns an empty list if the directory does not exist.
    """
    directory = Path(directory)
    if not directory.exists():
        return []

    index_path = directory / "MEMORY.md"
    entries: list[MemoryEntry] = []

    if index_path.exists():
        index_text = index_path.read_text(encoding="utf-8")
        for _desc, filename in _INDEX_LINK_RE.findall(index_text):
            file_path = directory / filename
            entry = _read_entry(file_path)
            if entry is not None:
                entries.append(entry)
    else:
        for file_path in sorted(directory.glob("*.md")):
            if file_path.name == "MEMORY.md":
                continue
            entry = _read_entry(file_path)
            if entry is not None:
                entries.append(entry)

    return entries


def write_memory(entry: MemoryEntry, expected_mtime: float | None = None) -> None:
    """Write *entry* back to disk atomically.

    If *expected_mtime* is given and the file's current mtime differs from it,
    raises :exc:`MtimeConflictError` without modifying the file.
    """
    path = entry.path
    if expected_mtime is not None:
        try:
            current_mtime = path.stat().st_mtime
        except FileNotFoundError:
            current_mtime = 0.0
        if current_mtime != expected_mtime:
            raise MtimeConflictError(
                f"File {path} was modified externally "
                f"(expected mtime {expected_mtime}, got {current_mtime})"
            )

    text = _render_frontmatter(entry)
    dir_ = path.parent
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    entry.mtime = path.stat().st_mtime


def _make_slug(name: str) -> str:
    slug = _SLUG_RE.sub("_", name.lower()).strip("_")
    return slug or "memory"


def _update_index(directory: Path, filename: str, name: str) -> None:
    """Append an entry to MEMORY.md, creating it if necessary."""
    index_path = directory / "MEMORY.md"
    if index_path.exists():
        text = index_path.read_text(encoding="utf-8")
    else:
        text = "# Memory Index\n"

    new_line = f"- [{name}]({filename})\n"
    if not text.endswith("\n"):
        text += "\n"
    text += new_line

    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_path, index_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def create_memory(
    directory: Path,
    *,
    name: str,
    type: str,
    description: str,
    content: str,
) -> MemoryEntry:
    """Create a new memory file in *directory* and register it in MEMORY.md."""
    directory = Path(directory)
    slug = _make_slug(name)
    filename = f"{slug}.md"
    # Avoid collisions
    counter = 1
    path = directory / filename
    while path.exists():
        filename = f"{slug}_{counter}.md"
        path = directory / filename
        counter += 1

    entry = MemoryEntry(
        path=path,
        name=name,
        description=description,
        type=type,
        content=content,
        mtime=0.0,
    )
    text = _render_frontmatter(entry)
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    entry.mtime = path.stat().st_mtime
    _update_index(directory, filename, name)
    return entry


def _remove_index_entry(directory: Path, filename: str) -> None:
    """Remove the line referencing *filename* from MEMORY.md."""
    index_path = directory / "MEMORY.md"
    if not index_path.exists():
        return
    lines = index_path.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines = [ln for ln in lines if filename not in ln]
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.writelines(new_lines)
        os.replace(tmp_path, index_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def delete_memory(entry: MemoryEntry) -> None:
    """Delete the memory file and remove it from MEMORY.md."""
    directory = entry.path.parent
    filename = entry.path.name
    try:
        entry.path.unlink()
    except FileNotFoundError:
        pass
    _remove_index_entry(directory, filename)
