"""Parses JSONL session files — zero gi imports."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from pathlib import Path

logger = logging.getLogger(__name__)


class MessageType(Enum):
    USER = auto()
    ASSISTANT = auto()
    PROGRESS = auto()
    FILE_SNAPSHOT = auto()


_TYPE_MAP = {
    "user": MessageType.USER,
    "assistant": MessageType.ASSISTANT,
    "progress": MessageType.PROGRESS,
    "file-history-snapshot": MessageType.FILE_SNAPSHOT,
}


@dataclass
class ParsedMessage:
    type: MessageType
    text: str
    timestamp: datetime | None
    uuid: str
    is_sidechain: bool = False


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return str(content)


def _ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


class SessionParser:
    def __init__(self, include_progress: bool = False, include_snapshots: bool = False):
        self.include_progress = include_progress
        self.include_snapshots = include_snapshots

    def parse(self, path: Path) -> list[ParsedMessage]:
        results = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            logger.warning("Cannot read %s: %s", path, e)
            raise
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("Skipping malformed line in %s", path)
                continue
            t = obj.get("type", "")
            if t == "queue-operation":
                continue
            msg_type = _TYPE_MAP.get(t)
            if msg_type is None:
                continue
            if msg_type == MessageType.PROGRESS and not self.include_progress:
                continue
            if msg_type == MessageType.FILE_SNAPSHOT and not self.include_snapshots:
                continue
            inner = obj.get("message", {})
            content = inner.get("content", "") if isinstance(inner, dict) else ""
            text = _text(content)
            if not text:
                continue
            results.append(ParsedMessage(
                type=msg_type, text=text,
                timestamp=_ts(obj.get("timestamp")),
                uuid=obj.get("uuid", ""),
                is_sidechain=obj.get("isSidechain", False),
            ))
        return results
