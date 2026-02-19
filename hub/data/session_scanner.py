"""Scans ~/.claude/projects/ — zero gi imports."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)
DEFAULT_PROJECTS_ROOT = Path.home() / ".claude" / "projects"


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


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


@dataclass
class ProjectInfo:
    original_path: str
    project_dir: Path
    sessions: list[SessionInfo] = field(default_factory=list)

    @property
    def last_active(self) -> datetime:
        if not self.sessions:
            return datetime.min.replace(tzinfo=timezone.utc)
        return max(s.modified for s in self.sessions)

    @property
    def exists_on_disk(self) -> bool:
        return Path(self.original_path).exists()


def _read_jsonl_metadata(jsonl_path: Path, original_path: str) -> SessionInfo | None:
    """Extract SessionInfo by scanning a JSONL file directly (no index entry)."""
    session_id = jsonl_path.stem
    first_prompt = ""
    git_branch = ""
    is_sidechain = False
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    message_count = 0
    try:
        with jsonl_path.open() as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_str = obj.get("timestamp", "")
                if ts_str:
                    try:
                        ts = _parse_iso(ts_str)
                        if first_ts is None:
                            first_ts = ts
                        last_ts = ts
                    except ValueError:
                        pass
                if not git_branch:
                    git_branch = obj.get("gitBranch", "")
                if obj.get("isSidechain"):
                    is_sidechain = True
                msg_type = obj.get("type", "")
                if msg_type in ("user", "assistant"):
                    message_count += 1
                    if msg_type == "user" and not first_prompt:
                        msg = obj.get("message", {})
                        content = msg.get("content", "")
                        if isinstance(content, list):
                            first_prompt = next(
                                (c.get("text", "") for c in content if c.get("type") == "text"),
                                "",
                            )
                        else:
                            first_prompt = str(content)
    except OSError as exc:
        logger.warning("Cannot read %s: %s", jsonl_path, exc)
        return None
    try:
        fallback = datetime.fromtimestamp(jsonl_path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        fallback = datetime.now(tz=timezone.utc)
    return SessionInfo(
        session_id=session_id,
        first_prompt=first_prompt[:200],
        message_count=message_count,
        created=first_ts or fallback,
        modified=last_ts or fallback,
        git_branch=git_branch,
        project_path=original_path,
        is_sidechain=is_sidechain,
        jsonl_path=jsonl_path,
    )


class SessionScanner:
    def __init__(self, projects_root: Path | None = None):
        self.projects_root = projects_root or DEFAULT_PROJECTS_ROOT

    def scan(self) -> list[ProjectInfo]:
        if not self.projects_root.exists():
            logger.warning("Projects root not found: %s", self.projects_root)
            return []
        results = []
        for proj_dir in sorted(self.projects_root.iterdir()):
            if not proj_dir.is_dir():
                continue
            idx = proj_dir / "sessions-index.json"
            if not idx.exists():
                continue
            try:
                data = json.loads(idx.read_text())
                original_path = data.get("originalPath", "")
                if not original_path:
                    continue
                project = ProjectInfo(original_path=original_path, project_dir=proj_dir)
                indexed_ids: set[str] = set()
                for e in data.get("entries", []):
                    sid = e["sessionId"]
                    indexed_ids.add(sid)
                    project.sessions.append(SessionInfo(
                        session_id=sid,
                        first_prompt=e.get("firstPrompt", ""),
                        message_count=e.get("messageCount", 0),
                        created=_parse_iso(e["created"]),
                        modified=_parse_iso(e["modified"]),
                        git_branch=e.get("gitBranch", ""),
                        project_path=e.get("projectPath", original_path),
                        is_sidechain=e.get("isSidechain", False),
                        jsonl_path=proj_dir / f"{sid}.jsonl",
                    ))
                # Pick up any .jsonl files not listed in the index
                for jsonl in proj_dir.glob("*.jsonl"):
                    if jsonl.stem not in indexed_ids:
                        info = _read_jsonl_metadata(jsonl, original_path)
                        if info:
                            project.sessions.append(info)
                results.append(project)
            except Exception as exc:
                logger.warning("Skipping %s: %s", proj_dir, exc)
        return results
