# Agent Configuration & Memory Editor Design

## Problem

ClaudeDossier has a CLAUDE.md viewer/editor for one agent. But users work with three agents (Claude Code, Codex CLI, Anti-Gravity), each with its own instruction files, configuration, and memory. There's no unified view to see and edit what each agent knows about a project.

## Current State

The existing `ProjectPage` (`hub/ui/project_viewer.py`) shows:
- Project metadata (path, session count, last active)
- CLAUDE.md inheritance chain (global → ancestors → project), with the project-level file editable

## What Each Agent Has

| | Claude Code | Codex CLI | Anti-Gravity |
|---|---|---|---|
| **Global instructions** | `~/.claude/CLAUDE.md` | `~/.codex/config.toml` | `~/.gemini/GEMINI.md` |
| **Project instructions** | `$PROJECT/CLAUDE.md` | `$PROJECT/AGENTS.md` | — |
| **Memory** | `~/.claude/projects/<encoded>/memory/*.md` with MEMORY.md index | `~/.codex/memories/` (exists, empty on this system) | — |
| **Brain artifacts** | — | — | `brain/{conv-id}/task.md, implementation_plan.md, walkthrough.md` (read-only AI outputs) |

## Design

### Tabbed Agent View

Expand `ProjectPage` into a tabbed layout with one tab per agent that has data for the current project. Tabs only appear when the agent has relevant files.

**Tab visibility rules:**
- **Claude** tab: Always shown (every project is a potential Claude project)
- **Codex** tab: Shown if project has Codex sessions, an `AGENTS.md`, or a trust entry in `config.toml`
- **Anti-Gravity** tab: Shown if project has AG sessions or brain data

### Claude Tab

**Instructions section** (existing, refactored):
- Same CLAUDE.md chain as today: cards from global → project, project-level editable with Save
- No functional change — just moved into a tab

**Memory section** (new):
- `Adw.PreferencesGroup` titled "Memory"
- Lists memory files from `~/.claude/projects/<encoded-path>/memory/`
- Each memory shown as an `Adw.ExpanderRow`:
  - Title: memory `name` from frontmatter
  - Subtitle: `description` from frontmatter + type badge (`user`, `feedback`, `project`, `reference`)
  - Expanded: `Gtk.TextView` with the memory content (below frontmatter), editable
  - Save button per memory
- "New Memory" action row at the bottom → creates file with frontmatter template, adds to MEMORY.md
- "Delete" button per memory → removes file + MEMORY.md entry (with confirmation)

**Memory frontmatter format** (existing convention):
```yaml
---
name: Feature status
description: Clear separation of robust working features vs broken
type: project
---

Content here...
```

### Codex Tab

**Config section** (read-only):
- Show the project's trust level from `config.toml` (if present)
- Show model and approval policy
- Subtitle: "Edit at ~/.codex/config.toml" (not editable in-app — TOML editing is fragile)

**Instructions section**:
- `$PROJECT/AGENTS.md` — editable card with Save (same pattern as CLAUDE.md)
- If file doesn't exist: "No AGENTS.md found" + "Create" button → creates with template

**Memory section**:
- List files from `~/.codex/memories/` (if any exist)
- Same ExpanderRow pattern as Claude memory
- If empty: "No Codex memories" dimmed label

### Anti-Gravity Tab

**Instructions section**:
- `~/.gemini/GEMINI.md` — editable card with Save (global, affects all AG sessions)
- Note: "This is a global file — changes affect all Anti-Gravity sessions"

**Brain artifacts section** (read-only):
- List brain conversations that overlap with this project (matched by session data)
- Each shown as a collapsible card: task.md, implementation_plan.md, walkthrough.md
- Read-only — these are AI outputs, not user instructions

## New Files

### `hub/data/agent_config.py`

Discovers what configuration and memory each agent has for a given project path.

```python
@dataclass
class AgentConfig:
    agent: str                           # "claude", "codex", "antigravity"
    global_instructions: Path | None     # Global instruction file
    project_instructions: Path | None    # Per-project instruction file
    memory_dir: Path | None              # Memory directory (if exists)
    memory_files: list[Path]             # Individual memory files
    config_file: Path | None             # Structured config (config.toml)
    brain_dirs: list[Path]               # Brain artifact directories (AG only)
    has_data: bool                       # Whether this agent has anything for this project
```

Key function:
```python
def discover_agent_configs(project_path: str, project_sessions: list) -> list[AgentConfig]:
    """Return configs for each agent that has data for this project."""
```

### `hub/data/memory_reader.py`

Reads and writes Claude memory files with YAML frontmatter.

```python
@dataclass
class MemoryEntry:
    path: Path
    name: str
    description: str
    type: str          # user, feedback, project, reference
    content: str       # Everything below the frontmatter

def read_memory_dir(memory_dir: Path) -> list[MemoryEntry]
def write_memory(entry: MemoryEntry) -> None
def create_memory(memory_dir: Path, name: str, type: str, content: str) -> MemoryEntry
def delete_memory(entry: MemoryEntry) -> None  # removes file + updates MEMORY.md
```

### `hub/ui/memory_editor.py`

GTK widget for displaying and editing memory entries. Used inside the Claude and Codex tabs.

```python
class MemoryEditor(Adw.PreferencesGroup):
    """List of memory entries with expand-to-edit UX."""
    def __init__(self, memory_dir: Path)
    def refresh(self)
```

### Modified: `hub/ui/project_viewer.py`

Refactored from single CLAUDE.md view to tabbed multi-agent view.

- `ProjectPage` gains an `Adw.ViewStack` (or `Gtk.Notebook`) for agent tabs
- Existing CLAUDE.md chain code moves into the Claude tab builder
- New tab builders for Codex and Anti-Gravity
- `load(project)` now calls `discover_agent_configs()` and builds tabs dynamically

## Scope

**In scope:**
- `hub/data/agent_config.py` — agent config discovery
- `hub/data/memory_reader.py` — memory CRUD with frontmatter
- `hub/ui/memory_editor.py` — memory list/edit widget
- `hub/ui/project_viewer.py` — refactor to tabbed multi-agent view
- Claude tab: instructions chain + memory editor
- Codex tab: read-only config + AGENTS.md editor
- Anti-Gravity tab: GEMINI.md editor + read-only brain artifacts

**Deferred:**
- config.toml in-app editing (show read-only)
- Creating AGENTS.md/GEMINI.md from scratch (show "Create" button, wire later)
- Memory frontmatter schema validation
- Diff view between global and project instructions
- Memory search/filter

## Testing Strategy

1. **Unit tests for `memory_reader.py`**: Read/write/create/delete memory files with frontmatter, MEMORY.md index updates
2. **Unit tests for `agent_config.py`**: Discovery logic with various project states (has Claude only, has all three, has none)
3. **Manual UI test**: Open project page, verify tabs appear correctly, edit memory, save, verify file on disk
