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
    agent_source: str = "claude"


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
        agent_source="claude",
    )


class ClaudeScanner:
    def __init__(self, projects_root: Path | None = None):
        self.projects_root = projects_root or DEFAULT_PROJECTS_ROOT

    def scan(self) -> list[ProjectInfo]:
        if not self.projects_root.exists():
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
                        agent_source="claude",
                    ))
                for jsonl in proj_dir.glob("*.jsonl"):
                    if jsonl.stem not in indexed_ids:
                        info = _read_jsonl_metadata(jsonl, original_path)
                        if info:
                            project.sessions.append(info)
                results.append(project)
            except Exception as exc:
                logger.warning("Skipping %s: %s", proj_dir, exc)
        return results

class CodexScanner:
    def __init__(self, codex_root: Path | None = None, sqlite_path: Path | None = None):
        self.codex_root = codex_root or Path.home() / ".codex" / "sessions"
        self.sqlite_path = sqlite_path or Path.home() / ".codex" / "state_5.sqlite"

    def scan(self) -> list[ProjectInfo]:
        import re
        if not self.codex_root.exists():
            return []
        
        project_map: dict[str, ProjectInfo] = {}

        for jsonl in self.codex_root.rglob("*.jsonl"):
            cwd = str(self.codex_root)
            first_prompt = ""
            msg_count = 0
            first_ts = None
            last_ts = None

            try:
                with jsonl.open() as fh:
                    for line in fh:
                        if not line.strip(): continue
                        try:
                            obj = json.loads(line)
                        except: continue
                        
                        ts_str = obj.get("timestamp") or obj.get("ts")
                        if ts_str:
                            try:
                                if isinstance(ts_str, (int, float)):
                                    ts = datetime.fromtimestamp(ts_str, tz=timezone.utc)
                                else:
                                    ts = _parse_iso(ts_str)
                                if first_ts is None: first_ts = ts
                                last_ts = ts
                            except ValueError: pass

                        if "text" in obj and isinstance(obj.get("text"), str):
                            msg_count += 1
                            if obj.get("role") == "user" or not first_prompt:
                                first_prompt = obj["text"]
                        
                        payload = obj.get("payload", {})
                        if payload and payload.get("type") == "message":
                            role = payload.get("role")
                            contents = payload.get("content", [])
                            if role in ("user", "assistant"):
                                msg_count += 1
                                for c in contents:
                                    if c.get("type") in ("input_text", "text"):
                                        t = c.get("text", "")
                                        if "<cwd>" in t:
                                            m = re.search(r"<cwd>(.*?)</cwd>", t)
                                            if m: cwd = m.group(1).strip()
                                        
                                        if role == "user" and not first_prompt and not t.startswith("<permissions") and not t.startswith("<environment"):
                                            first_prompt = t

            except OSError:
                continue

            if not first_prompt:
                first_prompt = f"Codex Session {jsonl.stem}"

            try:
                fallback = datetime.fromtimestamp(jsonl.stat().st_mtime, tz=timezone.utc)
            except OSError:
                fallback = datetime.now(tz=timezone.utc)

            info = SessionInfo(
                session_id=jsonl.stem,
                first_prompt=first_prompt[:200],
                message_count=msg_count,
                created=first_ts or fallback,
                modified=last_ts or fallback,
                git_branch="",
                project_path=cwd,
                is_sidechain=False,
                jsonl_path=jsonl,
                agent_source="codex"
            )

            if cwd not in project_map:
                project_map[cwd] = ProjectInfo(original_path=cwd, project_dir=Path(cwd))
            project_map[cwd].sessions.append(info)

        # --- SQLite enrichment ---
        from hub.data.codex_sqlite import load_codex_threads
        seen_ids = {s.session_id for p in project_map.values() for s in p.sessions}

        for thread in load_codex_threads(self.sqlite_path):
            tid = thread["id"]
            if tid in seen_ids:
                # Enrich existing session with SQLite metadata
                for proj in project_map.values():
                    for s in proj.sessions:
                        if s.session_id == tid:
                            if not s.first_prompt or s.first_prompt.startswith("Codex Session"):
                                s.first_prompt = thread.get("title") or thread.get("first_user_message") or s.first_prompt
                            if not s.git_branch:
                                s.git_branch = thread.get("git_branch") or ""
                continue

            # New thread not in JSONL — create session from SQLite
            cwd = thread["cwd"]
            info = SessionInfo(
                session_id=tid,
                first_prompt=(thread.get("first_user_message") or thread.get("title") or f"Codex Thread {tid}")[:200],
                message_count=0,
                created=datetime.fromtimestamp(thread["created_at"], tz=timezone.utc),
                modified=datetime.fromtimestamp(thread["updated_at"], tz=timezone.utc),
                git_branch=thread.get("git_branch") or "",
                project_path=cwd,
                is_sidechain=False,
                jsonl_path=Path(thread.get("rollout_path") or ""),
                agent_source="codex",
            )
            if cwd not in project_map:
                project_map[cwd] = ProjectInfo(original_path=cwd, project_dir=Path(cwd))
            project_map[cwd].sessions.append(info)

        return list(project_map.values())


class AntiGravityScanner:
    def __init__(self, root: Path | None = None):
        self.root = root or Path.home() / ".gemini" / "antigravity" / "conversations"

    def scan(self) -> list[ProjectInfo]:
        if not self.root.exists():
            return []
        
        project = ProjectInfo(original_path=str(self.root), project_dir=self.root)
        
        for pbfile in self.root.glob("*.pb"):
            try:
                fallback = datetime.fromtimestamp(pbfile.stat().st_mtime, tz=timezone.utc)
            except OSError:
                fallback = datetime.now(tz=timezone.utc)

            # We will read actual messages in parser. For now, just generate a generic info.
            info = SessionInfo(
                session_id=pbfile.stem,
                first_prompt=f"Anti-Gravity Session {pbfile.stem}",
                message_count=1,  # Placeholder, parser will read exact
                created=fallback,
                modified=fallback,
                git_branch="",
                project_path=str(self.root),
                is_sidechain=False,
                jsonl_path=pbfile,
                agent_source="antigravity"
            )
            project.sessions.append(info)
            
        return [project] if project.sessions else []


class SessionScanner:
    def __init__(self, projects_root: Path | None = None, codex_root: Path | None = None,
                 antigravity_root: Path | None = None, codex_sqlite_path: Path | None = None):
        self.claude = ClaudeScanner(projects_root)
        if projects_root is not None and codex_root is None:
            codex_root = projects_root / ".codex_fake"
        if projects_root is not None and antigravity_root is None:
            antigravity_root = projects_root / ".ag_fake"
        self.codex = CodexScanner(codex_root, sqlite_path=codex_sqlite_path)
        self.antigravity = AntiGravityScanner(antigravity_root)

    def scan(self) -> list[ProjectInfo]:
        projects = []
        projects.extend(self.claude.scan())
        projects.extend(self.codex.scan())
        projects.extend(self.antigravity.scan())
        return projects
