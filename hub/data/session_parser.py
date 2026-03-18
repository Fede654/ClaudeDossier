"""Parses JSONL session files — zero gi imports."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
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
        parts = []
        for b in content:
            if not isinstance(b, dict):
                continue
            btype = b.get("type", "")
            if btype == "text":
                parts.append(b.get("text", ""))
            elif btype == "thinking":
                parts.append(f"*thinking:* {b.get('thinking', '')}")
            elif btype == "tool_use":
                name = b.get("name", "unknown")
                inp = json.dumps(b.get("input", {}), indent=2)
                parts.append(f"**{name}**\n```json\n{inp}\n```")
            elif btype == "tool_result":
                rc = b.get("content", "")
                if isinstance(rc, list):
                    rc = "\n".join(
                        x.get("text", "") for x in rc if isinstance(x, dict)
                    )
                parts.append(f"```\n{rc}\n```")
        return "\n\n".join(p for p in parts if p)
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
    """Parse Anti-Gravity conversation turns from the Electron SQLite state DB.

    The encrypted `.pb` files cannot be decoded directly (AES-GCM with Electron-managed keys).
    Instead we read the plaintext summaries stored by the UI in `state.vscdb` under the key
    ``antigravityUnifiedStateSync.trajectorySummaries``.  The conversation UUID is derived from
    the `.pb` filename (which equals the conversation ID).
    """

    _cache: dict | None = None  # class-level cache so we read vscdb once per process

    def __init__(self, include_progress: bool = False, include_snapshots: bool = False):
        self.include_progress = include_progress
        self.include_snapshots = include_snapshots

    @classmethod
    def _trajectories(cls) -> dict:
        if cls._cache is None:
            try:
                from hub.data.antigravity_vscdb import load_trajectories
                cls._cache = load_trajectories()
            except Exception as e:
                logger.warning("antigravity_vscdb load failed: %s", e)
                cls._cache = {}
        return cls._cache

    def parse(self, path: Path, archive_brain_root: Path | None = None) -> list[ParsedMessage]:
        results = []
        conv_id = path.name if path.is_dir() else path.stem

        # Brain-only session: path IS the brain directory
        if path.is_dir():
            from hub.data.antigravity_brain import load_brain
            brain = load_brain(path)
            has_brain = any(brain.get(k, "").strip() for k in ("task", "implementation_plan", "walkthrough"))
            if has_brain:
                results.append(ParsedMessage(
                    type=MessageType.USER,
                    text=f"*Anti-Gravity Brain — {conv_id}*",
                    timestamp=None, uuid=conv_id,
                ))
                for key, label in [("task", "Task"), ("implementation_plan", "Plan"), ("walkthrough", "Walkthrough")]:
                    text = brain.get(key, "")
                    if text.strip():
                        results.append(ParsedMessage(
                            type=MessageType.ASSISTANT,
                            text=f"**{label}**\n\n{text}",
                            timestamp=None, uuid=conv_id,
                        ))
            return results

        try:
            trajectories = self._trajectories()
            info = trajectories.get(conv_id)

            if info:
                title = info.get("title") or "Untitled"
                turns = info.get("turns") or []
                if turns:
                    # Emit a header entry then each turn
                    results.append(ParsedMessage(
                        type=MessageType.USER,
                        text=f"*Anti-Gravity session — **{title}***",
                        timestamp=None, uuid=conv_id,
                    ))
                    for turn_text in turns:
                        if turn_text.strip():
                            results.append(ParsedMessage(
                                type=MessageType.ASSISTANT,
                                text=turn_text,
                                timestamp=None, uuid=conv_id,
                            ))
                else:
                    results.append(ParsedMessage(
                        type=MessageType.ASSISTANT,
                        text=f"*(Anti-Gravity session «{title}» — no turn summaries cached yet)*",
                        timestamp=None, uuid=conv_id,
                    ))
            else:
                size_mb = path.stat().st_size / (1024 * 1024)
                results.append(ParsedMessage(
                    type=MessageType.ASSISTANT,
                    text=(
                        f"*(Opaque Anti-Gravity Session)*\n\n"
                        f"File: `{path.name}` ({size_mb:.2f} MB)\n\n"
                        f"No cached summary found in `state.vscdb` for this conversation yet.\n"
                        f"Open the session in the Anti-Gravity editor to populate the cache."
                    ),
                    timestamp=None, uuid=conv_id,
                ))
        except Exception as e:
            logger.warning("AntiGravityParser error for %s: %s", path, e)
            results.append(ParsedMessage(
                type=MessageType.ASSISTANT, text=f"*(Error parsing session: {e})*",
                timestamp=None, uuid=""
            ))

        # Check brain/ for this conversation (may have both .pb and brain/)
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

        return results


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
