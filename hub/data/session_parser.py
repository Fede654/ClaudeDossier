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


class ClaudeParser:
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

class CodexParser:
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
            if not line: continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError: continue

            ts_str = obj.get("timestamp") or obj.get("ts")
            timestamp = _ts(ts_str) if isinstance(ts_str, str) else (datetime.fromtimestamp(ts_str, tz=timezone.utc) if isinstance(ts_str, (int,float)) else None)

            if "text" in obj and isinstance(obj.get("text"), str):
                role = obj.get("role", "user") 
                msg_type = MessageType.USER if role == "user" else MessageType.ASSISTANT
                results.append(ParsedMessage(
                    type=msg_type, text=obj["text"],
                    timestamp=timestamp, uuid=""
                ))
                continue

            payload = obj.get("payload", {})
            if payload and payload.get("type") == "message":
                role = payload.get("role")
                if role == "user":
                    msg_type = MessageType.USER
                elif role in ("assistant", "model"):
                    msg_type = MessageType.ASSISTANT
                else:
                    msg_type = MessageType.PROGRESS
                
                content = payload.get("content", [])
                text = ""
                for c in content:
                    if c.get("type") in ("text", "input_text", "output_text"):
                        text += c.get("text", "")
                
                if text:
                    results.append(ParsedMessage(
                        type=msg_type, text=text,
                        timestamp=timestamp, uuid=""
                    ))

        return results


class AntiGravityParser:
    def __init__(self, include_progress: bool = False, include_snapshots: bool = False):
        self.include_progress = include_progress
        self.include_snapshots = include_snapshots

    def parse(self, path: Path) -> list[ParsedMessage]:
        results = []
        try:
            # The Anti-Gravity (Cortex) PB files are heavily nested/wrapped and often
            # compressed or encrypted. They fail standard protobuf struct guessing.
            # E.g. "Found END_GROUP before START_GROUP" or "Invalid wiretype 6"
            # Instead of crashing the UI, we just display a placeholder.
            size_mb = path.stat().st_size / (1024 * 1024)
            msg_text = (
                f"*(Opaque Anti-Gravity Session)*\n\n"
                f"File: `{path.name}` ({size_mb:.2f} MB)\n\n"
                f"These conversation logs are serialized Cortex Protobuf streams "
                f"that cannot be decoded as raw plaintext at this time.\n\n"
                f"To view the history, please use the Anti-Gravity (Cascade) native client."
            )
            results.append(ParsedMessage(
                type=MessageType.ASSISTANT, text=msg_text,
                timestamp=None, uuid=""
            ))
        except Exception as e:
            logger.warning("Cannot read PB metadata %s: %s", path, e)
            results.append(ParsedMessage(
                type=MessageType.ASSISTANT, text=f"*(Error stat-ing session file: {e})*",
                timestamp=None, uuid=""
            ))
        return results

class SessionParser:
    def __init__(self, agent_source: str = "claude", include_progress: bool = False, include_snapshots: bool = False):
        self.agent_source = agent_source
        if agent_source == "codex":
            self.delegate = CodexParser(include_progress, include_snapshots)
        elif agent_source == "antigravity":
            self.delegate = AntiGravityParser(include_progress, include_snapshots)
        else:
            self.delegate = ClaudeParser(include_progress, include_snapshots)

    def parse(self, path: Path) -> list[ParsedMessage]:
        return self.delegate.parse(path)
