"""
Reads Anti-Gravity conversation turns from the Electron SQLite state database.

Anti-Gravity stores conversation summaries (including full AI response text)
in ~/.config/Antigravity/User/globalStorage/state.vscdb under the key
'antigravityUnifiedStateSync.trajectorySummaries'.

The value is a base64-encoded Protobuf blob with the following structure:
  outer  → repeated field 1 (one per conversation)
  1.1    = conversation UUID (string)
  1.2    = per-turn blob (itself a nested Protobuf)
  1.2.1  = base64-encoded inner Protobuf
  inner  → field 1  = title (string)
          field 4   = session/notification UUID
          field 12* = first turn (Protobuf)
          field 14* = second turn (Protobuf, may repeat)
  turn   → field 1 → field 94 → field 2 = AI response text (string)
           field 1 → field 94 → field 1 = task/step title (string)

*Fields 12 and 14 are the only turn-level fields observed so far.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_VSCDB = Path.home() / ".config" / "Antigravity" / "User" / "globalStorage" / "state.vscdb"
_KEY = "antigravityUnifiedStateSync.trajectorySummaries"


# ---------------------------------------------------------------------------
# Protobuf wire-format helpers (no external dependency)
# ---------------------------------------------------------------------------

def _decode_varint(data: bytes, pos: int):
    result, shift = 0, 0
    while pos < len(data):
        b = data[pos]; pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def _read_field(data: bytes, pos: int):
    """Read one TLV field from *data* starting at *pos*.

    Returns ``(field_number, wire_type, value, new_pos)`` or ``None`` at EOF.
    """
    if pos >= len(data):
        return None
    try:
        tag, pos = _decode_varint(data, pos)
        wt, fn = tag & 7, tag >> 3
        if wt == 0:
            v, pos = _decode_varint(data, pos)
            return fn, 0, v, pos
        elif wt == 1:
            return fn, 1, data[pos:pos + 8], pos + 8
        elif wt == 2:
            l, pos = _decode_varint(data, pos)
            return fn, 2, data[pos:pos + l], pos + l
        elif wt == 5:
            return fn, 5, data[pos:pos + 4], pos + 4
    except Exception:
        pass
    return None


def _iter_fields(data: bytes):
    pos = 0
    while True:
        r = _read_field(data, pos)
        if r is None:
            break
        fn, wt, val, pos = r
        yield fn, wt, val


def _as_str(val: bytes) -> str | None:
    try:
        return val.decode("utf-8")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Parse a single turn blob (field 12 or 14 of the inner blob)
# ---------------------------------------------------------------------------

def _parse_turn_text(turn_blob: bytes) -> str | None:
    """Extract the AI response text from a turn Protobuf blob.

    Path: turn → field 1 → field 94 → field 2 (AI text)
                                     → field 1 (task title)
    """
    parts: list[str] = []

    for fn, wt, val in _iter_fields(turn_blob):
        if fn == 1 and wt == 2:
            # descend into field 1 of the turn
            for fn1, wt1, v1 in _iter_fields(val):
                if fn1 == 94 and wt1 == 2:
                    # field 94 inside field 1 contains the text
                    for fn2, wt2, v2 in _iter_fields(v1):
                        if fn2 in (1, 2) and wt2 == 2:
                            s = _as_str(v2)
                            if s and len(s) > 5:
                                parts.append(s)

    return "\n\n".join(parts) if parts else None


# ---------------------------------------------------------------------------
# Parse the trajectory summaries blob
# ---------------------------------------------------------------------------

def load_trajectories(vscdb_path: Path | None = None) -> dict[str, dict]:
    """Return a dict of conversation info keyed by conversation UUID.

    Each value is a dict with:
      - ``title`` (str | None)
      - ``session_id`` (str | None)
      - ``turns`` (list[str])  — AI response texts in order
    """
    db_path = vscdb_path or _DEFAULT_VSCDB
    if not db_path.exists():
        logger.warning("state.vscdb not found at %s", db_path)
        return {}

    # Copy to temp to avoid lock conflicts with the running app
    tmp = tempfile.NamedTemporaryFile(suffix=".vscdb", delete=False)
    try:
        shutil.copy2(db_path, tmp.name)
        tmp.close()
        return _parse_vscdb(Path(tmp.name))
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def _parse_vscdb(db_path: Path) -> dict[str, dict]:
    convos: dict[str, dict] = {}
    try:
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(f"SELECT value FROM ItemTable WHERE key='{_KEY}'").fetchone()
        conn.close()
    except Exception as e:
        logger.warning("Cannot read vscdb %s: %s", db_path, e)
        return convos

    if not row:
        return convos

    try:
        outer_raw = base64.b64decode(row[0])
    except Exception as e:
        logger.warning("Cannot base64-decode trajectory blob: %s", e)
        return convos

    for outer_fn, outer_wt, outer_val in _iter_fields(outer_raw):
        if outer_fn != 1 or outer_wt != 2:
            continue

        conv_id: str | None = None
        turn_blob: bytes | None = None

        for fn2, wt2, v2 in _iter_fields(outer_val):
            if fn2 == 1 and wt2 == 2:
                conv_id = _as_str(v2)
            elif fn2 == 2 and wt2 == 2:
                turn_blob = v2

        if not conv_id or turn_blob is None:
            continue

        info = {"title": None, "session_id": None, "turns": []}

        # field 2 → field 1 is the b64-encoded inner Protobuf
        r3 = _read_field(turn_blob, 0)
        if not r3:
            convos[conv_id] = info
            continue
        fn3, wt3, v3, _ = r3
        if fn3 != 1 or wt3 != 2:
            convos[conv_id] = info
            continue

        try:
            inner = base64.b64decode(_as_str(v3) or "" + "==")
        except Exception:
            convos[conv_id] = info
            continue

        for fn4, wt4, v4 in _iter_fields(inner):
            if fn4 == 1 and wt4 == 2:
                title = _as_str(v4)
                if title:
                    info["title"] = title
            elif fn4 == 4 and wt4 == 2:
                sid = _as_str(v4)
                if sid:
                    info["session_id"] = sid
            elif fn4 in (12, 14) and wt4 == 2:
                txt = _parse_turn_text(v4)
                if txt:
                    info["turns"].append(txt)

        convos[conv_id] = info

    return convos
