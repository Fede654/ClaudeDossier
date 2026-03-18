# Agent Configuration & Memory Editor Design

## Problem

ClaudeDossier has a CLAUDE.md viewer/editor for one agent. But users work with three agents (Claude Code, Codex CLI, Anti-Gravity), each with its own instruction files, configuration, and memory. There's no unified view to see and edit what each agent knows about a project.

## Current State

The existing `ProjectPage` (`hub/ui/project_viewer.py`, 186 lines) shows:
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

### Navigation: Adw.ViewStack + ViewSwitcherBar

Use `Adw.ViewStack` with an `Adw.ViewSwitcherBar` (in content area, not headerbar) for agent tabs. NOT `Gtk.Notebook` — ViewStack is the Adwaita-idiomatic pattern for page switching.

`ProjectPage` becomes a thin orchestrator: metadata group at the top (always visible), ViewStack below with per-agent pages. Each agent page is its own widget file (~80-120 lines each).

**Tab visibility rules:**
- **Claude** tab: Always shown (every project is a potential Claude project)
- **Codex** tab: Shown if project has Codex sessions, an `AGENTS.md`, or a trust entry in `config.toml`
- **Anti-Gravity** tab: Shown if project has AG sessions or brain data

**Empty states**: When a tab is visible but has no content yet, show `Adw.StatusPage` with a primary action ("Create project memory", "Create AGENTS.md", etc.).

### Claude Tab (`hub/ui/claude_tab.py`)

**Instructions section** (existing, refactored):
- Same CLAUDE.md chain as today: cards from global → project, project-level editable with Save
- Lower `min_content_height` to ~200-240 (from 480) so memory section is visible below
- Let the page scroll, not individual cards

**Memory section** (new):
- `Adw.PreferencesGroup` titled "Memory"
- Lists memory files from `~/.claude/projects/<encoded-path>/memory/`
- Each memory shown as an `Adw.ActionRow`:
  - Title: memory `name` from frontmatter
  - Subtitle: `description` from frontmatter + type badge (`user`, `feedback`, `project`, `reference`)
  - Row expand shows a short read-only preview (first ~3 lines of content)
  - "Edit" button → opens `Adw.Dialog` with `Gtk.TextView` (monospace, markdown), Save/Discard buttons
- "New Memory" action row → dialog collecting Name, Type (dropdown: project/user/feedback/reference), Description → creates file with frontmatter, adds to MEMORY.md
- "Delete" button per memory → confirmation dialog explaining Claude Code may recreate related notes → removes file + MEMORY.md entry

**Memory frontmatter format** (existing convention):
```yaml
---
name: Feature status
description: Clear separation of robust working features vs broken
type: project
---

Content here...
```

### Codex Tab (`hub/ui/codex_tab.py`)

**Config section** (read-only):
- Show the project's trust level from `config.toml` (if present)
- Show model and approval policy
- Subtitle: "Edit at ~/.codex/config.toml"

**Instructions section**:
- `$PROJECT/AGENTS.md` — editable card with Save (same pattern as CLAUDE.md)
- If file doesn't exist: `Adw.StatusPage` with "Create AGENTS.md" button

**Memory section**:
- List files from `~/.codex/memories/` (if any exist)
- Same ActionRow + dialog pattern as Claude memory
- If empty: "No Codex memories" dimmed label

### Anti-Gravity Tab (`hub/ui/antigravity_tab.py`)

**Instructions section**:
- `~/.gemini/GEMINI.md` — editable card with Save
- **Persistent `Adw.Banner`** warning: "This is a global file — changes affect all Anti-Gravity sessions"
- First save shows a confirmation dialog; persist "Don't warn again" in GSettings

**Brain artifacts section** (read-only):
- List brain conversations that overlap with this project (matched by session data)
- Each shown as a collapsible card: task.md, implementation_plan.md, walkthrough.md
- Read-only — these are AI outputs, not user instructions

## File Safety

All file writes use atomic operations (temp file + `os.replace`).

**Memory editing safety** (Claude Code may also edit these files concurrently):
- On write, check `expected_mtime` — if file mtime changed since last read, show "File changed externally" banner with Reload/Overwrite actions
- Watch memory directory with `Gio.FileMonitor` — toast on save, banner on external change
- MEMORY.md index: auto-regenerate from directory listing only when index matches known template format; otherwise provide explicit "Rebuild Index" action

**Global file safety** (GEMINI.md, config.toml):
- Before any write to a global file, create a timestamped `.bak` in the same directory
- On error, restore from backup and show error toast

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

Reads and writes Claude memory files with YAML frontmatter. All writes are atomic.

```python
@dataclass
class MemoryEntry:
    path: Path
    name: str
    description: str
    type: str          # user, feedback, project, reference
    content: str       # Everything below the frontmatter
    mtime: float       # For expected_mtime safety checks

def read_memory_dir(memory_dir: Path) -> list[MemoryEntry]
def write_memory(entry: MemoryEntry, expected_mtime: float | None = None) -> None
def create_memory(memory_dir: Path, name: str, type: str, description: str, content: str) -> MemoryEntry
def delete_memory(entry: MemoryEntry) -> None  # removes file + updates MEMORY.md
def rebuild_memory_index(memory_dir: Path) -> None  # regenerate MEMORY.md from directory
```

### `hub/ui/memory_editor.py`

GTK widget for displaying and editing memory entries. List + edit dialog pattern.

```python
class MemoryEditor(Adw.PreferencesGroup):
    """List of memory entries with preview rows and edit/new/delete actions."""
    def __init__(self, memory_dir: Path)
    def refresh(self)
    # Signals: 'memory-changed' (emitted after save/create/delete)
```

### `hub/ui/claude_tab.py`, `hub/ui/codex_tab.py`, `hub/ui/antigravity_tab.py`

Per-agent page widgets (~80-120 lines each). Each is an `Adw.PreferencesPage`.

### Modified: `hub/ui/project_viewer.py`

Becomes thin orchestrator (~60-80 lines):
- Project metadata group (unchanged)
- `Adw.ViewStack` + `Adw.ViewSwitcherBar`
- `load(project)` calls `discover_agent_configs()` and creates/shows/hides tabs

## Scope

**In scope:**
- `hub/data/agent_config.py` — agent config discovery
- `hub/data/memory_reader.py` — memory CRUD with frontmatter + atomic writes + mtime safety
- `hub/ui/memory_editor.py` — memory list/edit widget with Adw.Dialog
- `hub/ui/claude_tab.py` — instructions chain + memory editor
- `hub/ui/codex_tab.py` — read-only config + AGENTS.md editor + empty state
- `hub/ui/antigravity_tab.py` — GEMINI.md editor with banner + read-only brain
- `hub/ui/project_viewer.py` — refactor to Adw.ViewStack orchestrator

**Deferred:**
- config.toml in-app editing (show read-only for v1)
- Memory frontmatter schema validation
- Diff view between global and project instructions
- Memory search/filter
- Gio.FileMonitor for external changes (add after core CRUD works)
- "Don't warn again" GSettings key for GEMINI.md save confirmation

## Testing Strategy

1. **Unit tests for `memory_reader.py`**: Read/write/create/delete memory files with frontmatter, MEMORY.md index updates, mtime safety check, atomic write verification
2. **Unit tests for `agent_config.py`**: Discovery logic with various project states (Claude only, all three, none)
3. **Manual UI test**: Open project page, verify tabs appear correctly, edit memory, save, verify file on disk
