"""Discover agent configuration files for a given project."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentConfig:
    agent: str
    global_instructions: Path | None = None
    project_instructions: Path | None = None
    memory_dir: Path | None = None
    memory_files: list[Path] = field(default_factory=list)
    config_file: Path | None = None
    brain_dirs: list[Path] = field(default_factory=list)
    has_data: bool = False


_CLAUDE_GLOBAL = Path.home() / ".claude" / "CLAUDE.md"
_CODEX_CONFIG = Path.home() / ".codex" / "config.toml"
_CODEX_MEMORIES = Path.home() / ".codex" / "memories"
_AG_GLOBAL = Path.home() / ".gemini" / "GEMINI.md"
_AG_BRAIN = Path.home() / ".gemini" / "antigravity" / "brain"


def _claude_memory_dir(project_path: str) -> Path:
    encoded = project_path.replace("/", "-")
    return Path.home() / ".claude" / "projects" / encoded / "memory"


def discover_agent_configs(
    project_path: str,
    project_sessions: list,
    claude_global: Path | None = None,
    claude_memory_dir: Path | None = None,
    codex_config: Path | None = None,
    codex_memories: Path | None = None,
    ag_global: Path | None = None,
    ag_brain: Path | None = None,
) -> list[AgentConfig]:
    proj = Path(project_path)

    # Claude — always shown
    cg = claude_global or _CLAUDE_GLOBAL
    cm = claude_memory_dir or _claude_memory_dir(project_path)
    claude_proj = proj / "CLAUDE.md"
    mem_files = sorted(cm.glob("*.md")) if cm.exists() else []
    mem_files = [f for f in mem_files if f.name != "MEMORY.md"]

    claude = AgentConfig(
        agent="claude",
        global_instructions=cg if cg.exists() else None,
        project_instructions=claude_proj if claude_proj.exists() else None,
        memory_dir=cm if cm.exists() else cm,
        memory_files=mem_files,
        has_data=True,
    )

    # Codex
    cc = codex_config or _CODEX_CONFIG
    codex_proj = proj / "AGENTS.md"
    codex_mems = codex_memories or _CODEX_MEMORIES
    codex_mem_files = sorted(codex_mems.glob("*.md")) if codex_mems.exists() else []
    has_codex_sessions = any(getattr(s, "agent_source", "") == "codex" for s in project_sessions)
    codex = AgentConfig(
        agent="codex",
        config_file=cc if cc.exists() else None,
        project_instructions=codex_proj if codex_proj.exists() else None,
        memory_dir=codex_mems if codex_mems.exists() else None,
        memory_files=codex_mem_files,
        has_data=(codex_proj.exists() or has_codex_sessions),
    )

    # Anti-Gravity
    ag = ag_global or _AG_GLOBAL
    ab = ag_brain or _AG_BRAIN
    brain_dirs = sorted(ab.iterdir()) if ab.exists() else []
    brain_dirs = [d for d in brain_dirs if d.is_dir()]
    has_ag_sessions = any(getattr(s, "agent_source", "") == "antigravity" for s in project_sessions)
    antigravity = AgentConfig(
        agent="antigravity",
        global_instructions=ag if ag.exists() else None,
        brain_dirs=brain_dirs,
        has_data=(ag.exists() or bool(brain_dirs) or has_ag_sessions),
    )

    return [claude, codex, antigravity]
