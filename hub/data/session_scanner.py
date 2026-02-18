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
                for e in data.get("entries", []):
                    project.sessions.append(SessionInfo(
                        session_id=e["sessionId"],
                        first_prompt=e.get("firstPrompt", ""),
                        message_count=e.get("messageCount", 0),
                        created=_parse_iso(e["created"]),
                        modified=_parse_iso(e["modified"]),
                        git_branch=e.get("gitBranch", ""),
                        project_path=e.get("projectPath", original_path),
                        is_sidechain=e.get("isSidechain", False),
                        jsonl_path=proj_dir / f"{e['sessionId']}.jsonl",
                    ))
                results.append(project)
            except Exception as exc:
                logger.warning("Skipping %s: %s", proj_dir, exc)
        return results
