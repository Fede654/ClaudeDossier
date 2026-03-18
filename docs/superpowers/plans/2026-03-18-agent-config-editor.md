# Agent Configuration & Memory Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the project page from a single CLAUDE.md viewer into a tabbed multi-agent configuration and memory editor using Adw.ViewStack.

**Architecture:** Data layer (`agent_config.py`, `memory_reader.py`) discovers and manages agent files. UI layer splits into per-agent page widgets (`claude_tab.py`, `codex_tab.py`, `antigravity_tab.py`) orchestrated by a thin `project_viewer.py`. Memory editing uses list rows + Adw.Dialog pattern.

**Tech Stack:** Python 3.10+, GTK 4, libadwaita 1.4+, PyGObject, pathlib, pytest

**Spec:** `docs/superpowers/specs/2026-03-18-agent-config-editor-design.md`

---

## File Structure

| File | Responsibility | Task |
|------|---------------|------|
| `hub/data/memory_reader.py` | **CREATE** — CRUD for memory files with YAML frontmatter | 1 |
| `hub/data/agent_config.py` | **CREATE** — Discover agent configs per project | 2 |
| `hub/ui/claude_tab.py` | **CREATE** — Claude instructions chain + memory editor | 3 |
| `hub/ui/codex_tab.py` | **CREATE** — Codex config view + AGENTS.md editor | 4 |
| `hub/ui/antigravity_tab.py` | **CREATE** — GEMINI.md editor + brain artifacts | 4 |
| `hub/ui/memory_editor.py` | **CREATE** — Reusable memory list + edit dialog widget | 3 |
| `hub/ui/project_viewer.py` | **REWRITE** — Thin ViewStack orchestrator | 5 |
| `tests/test_memory_reader.py` | **CREATE** — Memory CRUD tests | 1 |
| `tests/test_agent_config.py` | **CREATE** — Discovery tests | 2 |

---

### Task 1: Memory Reader (Data Layer)

**Context:** CRUD for Claude Code memory files. Each file has YAML frontmatter (name, description, type) followed by markdown content. An index file (`MEMORY.md`) links to all memories. All writes must be atomic (temp + `os.replace`).

**Files:**
- Create: `hub/data/memory_reader.py`
- Create: `tests/test_memory_reader.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_memory_reader.py`:

```python
from pathlib import Path


def _make_memory(tmp_path, filename, name, desc, mtype, content):
    """Create a memory file with frontmatter."""
    path = tmp_path / filename
    path.write_text(f"---\nname: {name}\ndescription: {desc}\ntype: {mtype}\n---\n\n{content}\n")
    return path


def _make_index(tmp_path, entries):
    """Create a MEMORY.md index."""
    lines = ["# Memory Index\n"]
    for filename, desc in entries:
        lines.append(f"- [{desc}]({filename})\n")
    (tmp_path / "MEMORY.md").write_text("".join(lines))


def test_read_memory_dir(tmp_path):
    from hub.data.memory_reader import read_memory_dir
    _make_memory(tmp_path, "proj.md", "Project info", "Core project details", "project", "The project does X.")
    _make_memory(tmp_path, "user.md", "User prefs", "How user works", "user", "Prefers TDD.")
    _make_index(tmp_path, [("proj.md", "Project info"), ("user.md", "User prefs")])

    entries = read_memory_dir(tmp_path)
    assert len(entries) == 2
    names = {e.name for e in entries}
    assert names == {"Project info", "User prefs"}
    proj = next(e for e in entries if e.name == "Project info")
    assert proj.type == "project"
    assert "The project does X." in proj.content
    assert proj.description == "Core project details"


def test_read_memory_dir_empty(tmp_path):
    from hub.data.memory_reader import read_memory_dir
    assert read_memory_dir(tmp_path) == []
    assert read_memory_dir(tmp_path / "nonexistent") == []


def test_write_memory_atomic(tmp_path):
    from hub.data.memory_reader import read_memory_dir, write_memory
    _make_memory(tmp_path, "test.md", "Test", "A test", "project", "Original.")
    entries = read_memory_dir(tmp_path)
    entry = entries[0]
    entry.content = "Updated content."
    write_memory(entry)

    reloaded = read_memory_dir(tmp_path)
    assert reloaded[0].content.strip() == "Updated content."
    assert reloaded[0].name == "Test"  # frontmatter preserved


def test_write_memory_mtime_check(tmp_path):
    import time
    from hub.data.memory_reader import read_memory_dir, write_memory, MtimeConflictError
    _make_memory(tmp_path, "test.md", "Test", "A test", "project", "V1.")
    entries = read_memory_dir(tmp_path)
    entry = entries[0]
    old_mtime = entry.mtime

    # Simulate external edit
    time.sleep(0.05)
    (tmp_path / "test.md").write_text("---\nname: Test\ndescription: A test\ntype: project\n---\n\nExternal edit.\n")

    entry.content = "My edit."
    try:
        write_memory(entry, expected_mtime=old_mtime)
        assert False, "Should have raised MtimeConflictError"
    except MtimeConflictError:
        pass  # expected


def test_create_memory(tmp_path):
    from hub.data.memory_reader import create_memory, read_memory_dir
    _make_index(tmp_path, [])
    entry = create_memory(tmp_path, name="New mem", type="feedback", description="A feedback", content="Don't do X.")
    assert entry.path.exists()
    assert "New mem" in entry.path.read_text()

    # MEMORY.md updated
    index = (tmp_path / "MEMORY.md").read_text()
    assert "New mem" in index or entry.path.name in index


def test_delete_memory(tmp_path):
    from hub.data.memory_reader import read_memory_dir, delete_memory
    _make_memory(tmp_path, "doomed.md", "Doomed", "Will be deleted", "project", "Bye.")
    _make_index(tmp_path, [("doomed.md", "Doomed")])

    entries = read_memory_dir(tmp_path)
    delete_memory(entries[0])

    assert not (tmp_path / "doomed.md").exists()
    index = (tmp_path / "MEMORY.md").read_text()
    assert "doomed.md" not in index
```

- [ ] **Step 2: Run tests — verify fail**

Run: `GSETTINGS_BACKEND=memory pytest tests/test_memory_reader.py -v`

- [ ] **Step 3: Implement `hub/data/memory_reader.py`**

```python
"""Read/write Claude Code memory files with YAML frontmatter."""
from __future__ import annotations

import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class MtimeConflictError(Exception):
    """Raised when a file was modified externally since last read."""
    pass


@dataclass
class MemoryEntry:
    path: Path
    name: str
    description: str
    type: str
    content: str
    mtime: float

    @property
    def frontmatter(self) -> str:
        return f"---\nname: {self.name}\ndescription: {self.description}\ntype: {self.type}\n---"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter. Returns (fields_dict, body_after_frontmatter)."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fields = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip()
    body = text[m.end():]
    return fields, body


def read_memory_dir(memory_dir: Path) -> list[MemoryEntry]:
    """Read all memory files from a directory. Returns empty list if dir doesn't exist."""
    if not memory_dir.exists():
        return []
    entries = []
    for f in sorted(memory_dir.iterdir()):
        if not f.is_file() or f.suffix != ".md" or f.name == "MEMORY.md":
            continue
        try:
            text = f.read_text(encoding="utf-8")
            fields, body = _parse_frontmatter(text)
            if not fields.get("name"):
                continue  # not a valid memory file
            entries.append(MemoryEntry(
                path=f,
                name=fields.get("name", f.stem),
                description=fields.get("description", ""),
                type=fields.get("type", "project"),
                content=body.strip("\n"),
                mtime=f.stat().st_mtime,
            ))
        except OSError as e:
            logger.warning("Cannot read memory %s: %s", f, e)
    return entries


def write_memory(entry: MemoryEntry, expected_mtime: float | None = None) -> None:
    """Write a memory file atomically. Raises MtimeConflictError if file changed."""
    if expected_mtime is not None and entry.path.exists():
        current_mtime = entry.path.stat().st_mtime
        if abs(current_mtime - expected_mtime) > 0.001:
            raise MtimeConflictError(
                f"{entry.path.name} was modified externally "
                f"(expected mtime {expected_mtime}, got {current_mtime})"
            )
    text = f"{entry.frontmatter}\n\n{entry.content}\n"
    fd, tmp = tempfile.mkstemp(dir=entry.path.parent, suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as out:
            out.write(text)
        os.replace(tmp, entry.path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    entry.mtime = entry.path.stat().st_mtime


def create_memory(
    memory_dir: Path, name: str, type: str, description: str, content: str
) -> MemoryEntry:
    """Create a new memory file and update MEMORY.md index."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    filename = f"{type}_{slug}.md"
    path = memory_dir / filename
    # Avoid collision
    counter = 2
    while path.exists():
        path = memory_dir / f"{type}_{slug}_{counter}.md"
        counter += 1

    entry = MemoryEntry(
        path=path, name=name, description=description,
        type=type, content=content, mtime=0,
    )
    memory_dir.mkdir(parents=True, exist_ok=True)
    write_memory(entry)

    # Update MEMORY.md
    _add_to_index(memory_dir, path.name, description)
    return entry


def delete_memory(entry: MemoryEntry) -> None:
    """Delete a memory file and remove it from MEMORY.md index."""
    if entry.path.exists():
        entry.path.unlink()
    _remove_from_index(entry.path.parent, entry.path.name)


def _add_to_index(memory_dir: Path, filename: str, description: str) -> None:
    """Add a link to MEMORY.md."""
    index = memory_dir / "MEMORY.md"
    if index.exists():
        text = index.read_text(encoding="utf-8")
    else:
        text = "# Memory Index\n\n"
    text += f"- [{description}]({filename})\n"
    index.write_text(text, encoding="utf-8")


def _remove_from_index(memory_dir: Path, filename: str) -> None:
    """Remove a link from MEMORY.md."""
    index = memory_dir / "MEMORY.md"
    if not index.exists():
        return
    lines = index.read_text(encoding="utf-8").splitlines(keepends=True)
    filtered = [l for l in lines if filename not in l]
    index.write_text("".join(filtered), encoding="utf-8")
```

- [ ] **Step 4: Run tests — verify pass**

Run: `GSETTINGS_BACKEND=memory pytest tests/test_memory_reader.py -v`

- [ ] **Step 5: Run full suite**

Run: `GSETTINGS_BACKEND=memory pytest tests/ -v`

- [ ] **Step 6: Commit**

```bash
git add hub/data/memory_reader.py tests/test_memory_reader.py
git commit -m "feat(memory): CRUD for Claude memory files with frontmatter and atomic writes"
```

---

### Task 2: Agent Config Discovery (Data Layer)

**Context:** Given a project path and its sessions, discover what configuration each agent has: instruction files, memory directories, config files, brain artifacts.

**Files:**
- Create: `hub/data/agent_config.py`
- Create: `tests/test_agent_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_agent_config.py`:

```python
from pathlib import Path


def test_discovers_claude_config(tmp_path):
    from hub.data.agent_config import discover_agent_configs
    proj = tmp_path / "myproject"
    proj.mkdir()
    (proj / "CLAUDE.md").write_text("# Instructions")

    # Simulate memory dir
    mem = tmp_path / "claude_memory"
    mem.mkdir()
    (mem / "MEMORY.md").write_text("# Index\n")
    (mem / "proj.md").write_text("---\nname: Test\ndescription: x\ntype: project\n---\nContent\n")

    configs = discover_agent_configs(
        str(proj), [],
        claude_global=tmp_path / "global_claude.md",
        claude_memory_dir=mem,
    )
    claude = next(c for c in configs if c.agent == "claude")
    assert claude.has_data is True
    assert claude.project_instructions == proj / "CLAUDE.md"
    assert claude.memory_dir == mem
    assert len(claude.memory_files) == 1


def test_discovers_codex_config(tmp_path):
    from hub.data.agent_config import discover_agent_configs
    proj = tmp_path / "myproject"
    proj.mkdir()
    (proj / "AGENTS.md").write_text("# Agents")

    configs = discover_agent_configs(
        str(proj), [],
        codex_config=tmp_path / "config.toml",
    )
    codex = next(c for c in configs if c.agent == "codex")
    assert codex.has_data is True
    assert codex.project_instructions == proj / "AGENTS.md"


def test_discovers_antigravity_config(tmp_path):
    from hub.data.agent_config import discover_agent_configs
    gemini_md = tmp_path / "GEMINI.md"
    gemini_md.write_text("# Gemini agent")

    configs = discover_agent_configs(
        str(tmp_path / "proj"), [],
        ag_global=gemini_md,
    )
    ag = next(c for c in configs if c.agent == "antigravity")
    assert ag.has_data is True
    assert ag.global_instructions == gemini_md


def test_no_data_returns_empty_configs(tmp_path):
    from hub.data.agent_config import discover_agent_configs
    configs = discover_agent_configs(
        str(tmp_path / "empty"), [],
        claude_global=tmp_path / "nope.md",
    )
    # Claude always has_data (always shown)
    claude = next(c for c in configs if c.agent == "claude")
    assert claude.has_data is True  # always shown
    codex = next(c for c in configs if c.agent == "codex")
    assert codex.has_data is False
```

- [ ] **Step 2: Run tests — verify fail**

- [ ] **Step 3: Implement `hub/data/agent_config.py`**

```python
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
    """Derive the Claude memory directory for a project path."""
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
    """Return configs for each agent. Claude always has_data (always shown)."""
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
        memory_dir=cm if cm.exists() else cm,  # always set for create
        memory_files=mem_files,
        has_data=True,  # always shown
    )

    # Codex
    cc = codex_config or _CODEX_CONFIG
    codex_proj = proj / "AGENTS.md"
    codex_mems = codex_memories or _CODEX_MEMORIES
    codex_mem_files = sorted(codex_mems.glob("*.md")) if codex_mems.exists() else []
    has_codex_sessions = any(
        getattr(s, "agent_source", "") == "codex" for s in project_sessions
    )
    codex = AgentConfig(
        agent="codex",
        config_file=cc if cc.exists() else None,
        project_instructions=codex_proj if codex_proj.exists() else None,
        memory_dir=codex_mems if codex_mems.exists() else None,
        memory_files=codex_mem_files,
        has_data=(codex_proj.exists() or cc.exists() or has_codex_sessions),
    )

    # Anti-Gravity
    ag = ag_global or _AG_GLOBAL
    ab = ag_brain or _AG_BRAIN
    brain_dirs = sorted(ab.iterdir()) if ab.exists() else []
    brain_dirs = [d for d in brain_dirs if d.is_dir()]
    has_ag_sessions = any(
        getattr(s, "agent_source", "") == "antigravity" for s in project_sessions
    )
    antigravity = AgentConfig(
        agent="antigravity",
        global_instructions=ag if ag.exists() else None,
        brain_dirs=brain_dirs,
        has_data=(ag.exists() or bool(brain_dirs) or has_ag_sessions),
    )

    return [claude, codex, antigravity]
```

- [ ] **Step 4: Run tests — verify pass**

- [ ] **Step 5: Commit**

```bash
git add hub/data/agent_config.py tests/test_agent_config.py
git commit -m "feat(config): agent configuration discovery per project"
```

---

### Task 3: Memory Editor Widget + Claude Tab (UI)

**Context:** Create the reusable memory editor widget (list rows + edit dialog) and the Claude tab that uses it alongside the existing CLAUDE.md chain viewer. This is the most complex UI task.

**Files:**
- Create: `hub/ui/memory_editor.py`
- Create: `hub/ui/claude_tab.py`

- [ ] **Step 1: Create `hub/ui/memory_editor.py`**

```python
"""Reusable memory list + edit dialog widget."""
from __future__ import annotations

from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk, GObject

from hub.data.memory_reader import read_memory_dir, write_memory, create_memory, delete_memory, MemoryEntry, MtimeConflictError


class MemoryEditor(Adw.PreferencesGroup):
    __gtype_name__ = 'MemoryEditor'

    __gsignals__ = {
        'memory-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, memory_dir: Path):
        super().__init__(title="Memory")
        self._memory_dir = memory_dir
        self._entries: list[MemoryEntry] = []
        self.refresh()

    def refresh(self):
        # Clear existing rows
        child = self.get_first_child()
        # PreferencesGroup children are managed — rebuild by removing all action rows
        # Use a fresh build approach
        self._entries = read_memory_dir(self._memory_dir)

        # Remove all existing rows (skip the group header)
        while True:
            row = self._find_first_action_row()
            if row is None:
                break
            self.remove(row)

        if not self._entries:
            empty = Adw.ActionRow(title="No memories", subtitle="Memory files will appear here")
            empty.add_css_class("dim-label")
            self.add(empty)
        else:
            for entry in self._entries:
                row = self._make_row(entry)
                self.add(row)

        # "New Memory" button row
        new_row = Adw.ActionRow(title="New Memory...")
        new_row.set_activatable(True)
        new_row.add_prefix(Gtk.Image.new_from_icon_name("list-add-symbolic"))
        new_row.connect("activated", self._on_new_memory)
        self.add(new_row)

    def _find_first_action_row(self):
        """Find the first Adw.ActionRow child of this group (for removal)."""
        # Walk the listbox inside the group
        listbox = None
        child = self.get_first_child()
        while child:
            if isinstance(child, Gtk.ListBox):
                listbox = child
                break
            child = child.get_next_sibling()
        if listbox is None:
            return None
        row = listbox.get_first_child()
        if isinstance(row, Adw.ActionRow):
            return row
        return None

    def _make_row(self, entry: MemoryEntry) -> Adw.ActionRow:
        type_badges = {"user": "👤", "feedback": "💬", "project": "📋", "reference": "🔗"}
        badge = type_badges.get(entry.type, "📝")
        row = Adw.ActionRow(
            title=f"{badge}  {entry.name}",
            subtitle=entry.description,
        )
        row.set_activatable(True)
        row.connect("activated", lambda _, e=entry: self._on_edit(e))

        delete_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        delete_btn.set_valign(Gtk.Align.CENTER)
        delete_btn.add_css_class("flat")
        delete_btn.connect("clicked", lambda _, e=entry: self._on_delete(e))
        row.add_suffix(delete_btn)
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))

        return row

    def _on_edit(self, entry: MemoryEntry):
        """Open edit dialog for a memory entry."""
        dialog = Adw.Dialog()
        dialog.set_title(f"Edit: {entry.name}")
        dialog.set_content_width(600)
        dialog.set_content_height(500)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Header bar with Save/Discard
        hbar = Adw.HeaderBar()
        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        hbar.pack_end(save_btn)
        box.append(hbar)

        # Text editor
        tv = Gtk.TextView()
        tv.set_monospace(True)
        tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        tv.set_top_margin(12)
        tv.set_bottom_margin(12)
        tv.set_left_margin(12)
        tv.set_right_margin(12)
        tv.get_buffer().set_text(entry.content)

        sw = Gtk.ScrolledWindow(vexpand=True)
        sw.set_child(tv)
        box.append(sw)

        dialog.set_child(box)

        def on_save(_):
            buf = tv.get_buffer()
            entry.content = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
            try:
                write_memory(entry, expected_mtime=entry.mtime)
                self._toast("Saved")
                self.refresh()
                self.emit("memory-changed")
            except MtimeConflictError:
                self._toast("File changed externally — reload and retry")
            dialog.close()

        save_btn.connect("clicked", on_save)
        dialog.present(self.get_root())

    def _on_new_memory(self, _):
        """Dialog to create a new memory."""
        dialog = Adw.Dialog()
        dialog.set_title("New Memory")
        dialog.set_content_width(400)
        dialog.set_content_height(350)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        hbar = Adw.HeaderBar()
        create_btn = Gtk.Button(label="Create")
        create_btn.add_css_class("suggested-action")
        hbar.pack_end(create_btn)
        box.append(hbar)

        group = Adw.PreferencesGroup()
        name_row = Adw.EntryRow(title="Name")
        desc_row = Adw.EntryRow(title="Description")

        type_row = Adw.ComboRow(title="Type")
        types = Gtk.StringList.new(["project", "user", "feedback", "reference"])
        type_row.set_model(types)

        group.add(name_row)
        group.add(desc_row)
        group.add(type_row)
        box.append(group)
        dialog.set_child(box)

        def on_create(_):
            name = name_row.get_text().strip()
            desc = desc_row.get_text().strip()
            idx = type_row.get_selected()
            mtype = types.get_string(idx)
            if not name:
                return
            create_memory(self._memory_dir, name=name, type=mtype, description=desc, content="")
            self._toast(f"Created: {name}")
            self.refresh()
            self.emit("memory-changed")
            dialog.close()

        create_btn.connect("clicked", on_create)
        dialog.present(self.get_root())

    def _on_delete(self, entry: MemoryEntry):
        """Confirm and delete a memory."""
        dialog = Adw.AlertDialog()
        dialog.set_heading(f"Delete '{entry.name}'?")
        dialog.set_body("The file will be removed. Claude Code may recreate related notes in future sessions.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")

        def on_response(_, response):
            if response == "delete":
                delete_memory(entry)
                self._toast(f"Deleted: {entry.name}")
                self.refresh()
                self.emit("memory-changed")

        dialog.connect("response", on_response)
        dialog.present(self.get_root())

    def _toast(self, msg: str):
        win = self.get_root()
        if hasattr(win, "add_toast"):
            toast = Adw.Toast.new(msg)
            toast.set_timeout(2)
            win.add_toast(toast)
```

- [ ] **Step 2: Create `hub/ui/claude_tab.py`**

Extract the existing CLAUDE.md chain viewer from `project_viewer.py` into this file, add the memory editor below it.

```python
"""Claude Code configuration tab — instructions chain + memory editor."""
from __future__ import annotations

from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk

from hub.data.agent_config import AgentConfig


def _claude_chain(project_path: str) -> list[tuple[str, bool]]:
    """Walk up from project_path to $HOME, then ~/.claude/CLAUDE.md."""
    chain = []
    p = Path(project_path)
    home = Path.home()
    while True:
        candidate = p / "CLAUDE.md"
        chain.append((str(candidate), candidate.exists()))
        if p == home or p.parent == p:
            break
        p = p.parent
    global_cfg = home / ".claude" / "CLAUDE.md"
    chain.append((str(global_cfg), global_cfg.exists()))
    return chain


class ClaudeTab(Adw.PreferencesPage):
    __gtype_name__ = 'ClaudeTab'

    def __init__(self):
        super().__init__(title="Claude", icon_name="document-edit-symbolic")
        self._text_view = None
        self._project_path = None
        self._chain_group = Adw.PreferencesGroup(title="Instructions Chain")
        self._chain_group.set_description("Load order: global → project (only present files shown)")
        self._chain_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._chain_box.set_margin_top(4)
        self._chain_box.set_margin_bottom(8)
        self._chain_box.set_margin_start(6)
        self._chain_box.set_margin_end(6)
        self._chain_group.add(self._chain_box)
        self.add(self._chain_group)

        # Memory editor added dynamically in load()
        self._memory_editor = None

    def load(self, project_path: str, config: AgentConfig):
        self._project_path = project_path
        self._text_view = None
        self._rebuild_chain(project_path)
        self._rebuild_memory(config)

    def _rebuild_chain(self, project_path: str):
        # Clear chain box
        child = self._chain_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._chain_box.remove(child)
            child = nxt

        chain = _claude_chain(project_path)
        existing = [(p, e) for p, e in reversed(chain) if e]
        home = Path.home()
        proj = Path(project_path)

        if not existing:
            lbl = Gtk.Label(label="No CLAUDE.md files found in chain", xalign=0)
            lbl.add_css_class("dim-label")
            self._chain_box.append(lbl)
            return

        for idx, (path_str, _) in enumerate(existing):
            p = Path(path_str)
            is_project = (p.parent == proj)
            is_last = (idx == len(existing) - 1)

            if p == home / ".claude" / "CLAUDE.md":
                role = "Global  ·  ~/.claude/CLAUDE.md"
            elif is_project:
                rel = "~/" + str(p.relative_to(home)) if p.is_relative_to(home) else path_str
                role = f"Project  ·  {rel}"
            else:
                try:
                    rel = "~/" + str(p.relative_to(home))
                except ValueError:
                    rel = path_str
                role = rel

            try:
                content = p.read_text()
            except OSError:
                content = "(unreadable)"

            block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            block.add_css_class("card")
            block.set_margin_bottom(2)

            hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            hdr_box.set_margin_start(10)
            hdr_box.set_margin_top(8)
            hdr_box.set_margin_end(10)
            hdr_box.set_margin_bottom(6)

            hdr = Gtk.Label(label=role, xalign=0, hexpand=True)
            hdr.add_css_class("caption")
            hdr.add_css_class("heading")
            hdr_box.append(hdr)

            if is_last:
                save_btn = Gtk.Button(label="Save")
                save_btn.add_css_class("suggested-action")
                save_btn.set_valign(Gtk.Align.CENTER)
                save_btn.connect("clicked", self._save)
                hdr_box.append(save_btn)

            block.append(hdr_box)
            block.append(Gtk.Separator())

            tv = Gtk.TextView()
            tv.set_monospace(True)
            tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            tv.set_top_margin(8)
            tv.set_bottom_margin(8)
            tv.set_left_margin(10)
            tv.set_right_margin(10)
            tv.get_buffer().set_text(content)

            if is_last:
                self._text_view = tv
            else:
                tv.set_editable(False)
                tv.set_cursor_visible(False)

            sw = Gtk.ScrolledWindow()
            sw.set_min_content_height(200)
            sw.set_max_content_height(600)
            sw.set_propagate_natural_height(True)
            sw.set_child(tv)
            block.append(sw)
            self._chain_box.append(block)

    def _rebuild_memory(self, config: AgentConfig):
        if self._memory_editor:
            self.remove(self._memory_editor)
        if config.memory_dir:
            from hub.ui.memory_editor import MemoryEditor
            self._memory_editor = MemoryEditor(config.memory_dir)
            self.add(self._memory_editor)

    def _save(self, _):
        if not self._project_path or not self._text_view:
            return
        buf = self._text_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        target = Path(self._project_path) / "CLAUDE.md"
        try:
            target.write_text(text)
            self._toast(f"Saved {target.name}")
        except Exception as e:
            self._toast(f"Error: {e}")

    def _toast(self, msg: str):
        win = self.get_root()
        if hasattr(win, "add_toast"):
            toast = Adw.Toast.new(msg)
            toast.set_timeout(0)
            win.add_toast(toast)
            GLib.timeout_add(1500, toast.dismiss)
```

- [ ] **Step 3: Verify no import errors**

Run: `GSETTINGS_SCHEMA_DIR=builddir/data PYTHONPATH=. python3 -c "from hub.ui.claude_tab import ClaudeTab; print('OK')"`

- [ ] **Step 4: Commit**

```bash
git add hub/ui/memory_editor.py hub/ui/claude_tab.py
git commit -m "feat(ui): memory editor widget and Claude configuration tab"
```

---

### Task 4: Codex + Anti-Gravity Tabs (UI)

**Context:** Simpler tabs — Codex shows read-only config + editable AGENTS.md, AG shows editable GEMINI.md with warning banner + read-only brain artifacts.

**Files:**
- Create: `hub/ui/codex_tab.py`
- Create: `hub/ui/antigravity_tab.py`

- [ ] **Step 1: Create `hub/ui/codex_tab.py`**

```python
"""Codex CLI configuration tab — config.toml view + AGENTS.md editor."""
from __future__ import annotations

from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk

from hub.data.agent_config import AgentConfig


class CodexTab(Adw.PreferencesPage):
    __gtype_name__ = 'CodexTab'

    def __init__(self):
        super().__init__(title="Codex", icon_name="utilities-terminal-symbolic")
        self._agents_tv = None
        self._project_path = None

    def load(self, project_path: str, config: AgentConfig):
        self._project_path = project_path
        self._agents_tv = None

        # Clear previous content
        child = self.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.remove(child)
            child = nxt

        # Config section (read-only)
        if config.config_file:
            cfg_group = Adw.PreferencesGroup(title="Configuration")
            cfg_group.set_description(f"Read-only · {config.config_file}")
            try:
                import tomllib
                with open(config.config_file, "rb") as f:
                    toml = tomllib.load(f)
                model = toml.get("model", "unknown")
                policy = toml.get("approval_policy", "unknown")
                Adw.ActionRow(title="Model", subtitle=model) |> cfg_group.add
                cfg_group.add(Adw.ActionRow(title="Model", subtitle=model))
                cfg_group.add(Adw.ActionRow(title="Approval policy", subtitle=policy))
            except Exception:
                cfg_group.add(Adw.ActionRow(title="Could not parse config.toml"))
            self.add(cfg_group)

        # AGENTS.md section
        agents_group = Adw.PreferencesGroup(title="AGENTS.md")
        agents_path = Path(project_path) / "AGENTS.md"
        if agents_path.exists():
            agents_group.set_description(str(agents_path))
            block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            block.add_css_class("card")

            hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            hdr_box.set_margin_start(10)
            hdr_box.set_margin_top(8)
            hdr_box.set_margin_end(10)
            hdr_box.set_margin_bottom(6)
            hdr = Gtk.Label(label="Project instructions", xalign=0, hexpand=True)
            hdr.add_css_class("caption")
            hdr.add_css_class("heading")
            hdr_box.append(hdr)
            save_btn = Gtk.Button(label="Save")
            save_btn.add_css_class("suggested-action")
            save_btn.connect("clicked", self._save_agents)
            hdr_box.append(save_btn)
            block.append(hdr_box)
            block.append(Gtk.Separator())

            tv = Gtk.TextView()
            tv.set_monospace(True)
            tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            tv.set_top_margin(8)
            tv.set_bottom_margin(8)
            tv.set_left_margin(10)
            tv.set_right_margin(10)
            try:
                tv.get_buffer().set_text(agents_path.read_text())
            except OSError:
                tv.get_buffer().set_text("(unreadable)")
            self._agents_tv = tv

            sw = Gtk.ScrolledWindow()
            sw.set_min_content_height(200)
            sw.set_max_content_height(600)
            sw.set_propagate_natural_height(True)
            sw.set_child(tv)
            block.append(sw)
            agents_group.add(block)
        else:
            status = Adw.StatusPage()
            status.set_title("No AGENTS.md")
            status.set_description("Create an AGENTS.md file to provide instructions for Codex CLI in this project.")
            agents_group.add(status)
        self.add(agents_group)

    def _save_agents(self, _):
        if not self._project_path or not self._agents_tv:
            return
        buf = self._agents_tv.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        target = Path(self._project_path) / "AGENTS.md"
        try:
            target.write_text(text)
            self._toast(f"Saved {target.name}")
        except Exception as e:
            self._toast(f"Error: {e}")

    def _toast(self, msg: str):
        win = self.get_root()
        if hasattr(win, "add_toast"):
            win.add_toast(Adw.Toast.new(msg))
```

- [ ] **Step 2: Create `hub/ui/antigravity_tab.py`**

```python
"""Anti-Gravity configuration tab — GEMINI.md editor + brain artifacts."""
from __future__ import annotations

from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk

from hub.data.agent_config import AgentConfig


class AntiGravityTab(Adw.PreferencesPage):
    __gtype_name__ = 'AntiGravityTab'

    def __init__(self):
        super().__init__(title="Anti-Gravity", icon_name="weather-clear-symbolic")
        self._gemini_tv = None

    def load(self, config: AgentConfig):
        self._gemini_tv = None

        child = self.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.remove(child)
            child = nxt

        # GEMINI.md section
        if config.global_instructions:
            gemini_group = Adw.PreferencesGroup(title="GEMINI.md")
            gemini_group.set_description("Global · ~/.gemini/GEMINI.md")

            # Warning banner
            banner = Adw.Banner()
            banner.set_title("Global file — changes affect all Anti-Gravity sessions")
            banner.set_revealed(True)
            gemini_group.add(banner)

            block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            block.add_css_class("card")

            hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            hdr_box.set_margin_start(10)
            hdr_box.set_margin_top(8)
            hdr_box.set_margin_end(10)
            hdr_box.set_margin_bottom(6)
            hdr = Gtk.Label(label="Agent instructions", xalign=0, hexpand=True)
            hdr.add_css_class("caption")
            hdr.add_css_class("heading")
            hdr_box.append(hdr)
            save_btn = Gtk.Button(label="Save")
            save_btn.add_css_class("suggested-action")
            save_btn.connect("clicked", self._save_gemini)
            hdr_box.append(save_btn)
            block.append(hdr_box)
            block.append(Gtk.Separator())

            tv = Gtk.TextView()
            tv.set_monospace(True)
            tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            tv.set_top_margin(8)
            tv.set_bottom_margin(8)
            tv.set_left_margin(10)
            tv.set_right_margin(10)
            try:
                tv.get_buffer().set_text(config.global_instructions.read_text())
            except OSError:
                tv.get_buffer().set_text("(unreadable)")
            self._gemini_tv = tv
            self._gemini_path = config.global_instructions

            sw = Gtk.ScrolledWindow()
            sw.set_min_content_height(200)
            sw.set_max_content_height(600)
            sw.set_propagate_natural_height(True)
            sw.set_child(tv)
            block.append(sw)
            gemini_group.add(block)
            self.add(gemini_group)

        # Brain artifacts (read-only)
        if config.brain_dirs:
            brain_group = Adw.PreferencesGroup(title="Brain Artifacts")
            brain_group.set_description("Read-only AI-generated documents")
            for bdir in config.brain_dirs[:10]:  # limit display
                task_file = bdir / "task.md"
                if task_file.exists():
                    try:
                        preview = task_file.read_text()[:100].replace("\n", " ")
                    except OSError:
                        preview = "(unreadable)"
                    row = Adw.ActionRow(
                        title=bdir.name[:20] + "...",
                        subtitle=preview,
                    )
                    brain_group.add(row)
            self.add(brain_group)

    def _save_gemini(self, _):
        if not self._gemini_tv or not self._gemini_path:
            return
        import os, tempfile, shutil
        buf = self._gemini_tv.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        # Backup before writing global file
        bak = self._gemini_path.with_suffix(f".bak")
        try:
            shutil.copy2(self._gemini_path, bak)
        except OSError:
            pass
        try:
            self._gemini_path.write_text(text)
            self._toast(f"Saved {self._gemini_path.name}")
        except Exception as e:
            self._toast(f"Error: {e}")

    def _toast(self, msg: str):
        win = self.get_root()
        if hasattr(win, "add_toast"):
            win.add_toast(Adw.Toast.new(msg))
```

- [ ] **Step 3: Verify imports**

Run: `GSETTINGS_SCHEMA_DIR=builddir/data PYTHONPATH=. python3 -c "from hub.ui.codex_tab import CodexTab; from hub.ui.antigravity_tab import AntiGravityTab; print('OK')"`

- [ ] **Step 4: Commit**

```bash
git add hub/ui/codex_tab.py hub/ui/antigravity_tab.py
git commit -m "feat(ui): Codex and Anti-Gravity configuration tabs"
```

---

### Task 5: Project Viewer Refactor (Orchestrator)

**Context:** Rewrite `project_viewer.py` as a thin orchestrator: metadata group + Adw.ViewStack with per-agent tabs. Uses `discover_agent_configs()` to decide which tabs to show.

**Files:**
- Rewrite: `hub/ui/project_viewer.py`

- [ ] **Step 1: Rewrite `hub/ui/project_viewer.py`**

```python
"""Project metadata + multi-agent configuration tabs."""
from __future__ import annotations

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk

from hub.data.session_scanner import ProjectInfo


class ProjectPage(Gtk.Box):
    __gtype_name__ = 'ProjectPage'

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._project = None
        self._tabs = {}

        # Metadata header (always visible)
        self._meta_group = Adw.PreferencesGroup(title="Project")
        self._meta_group.set_margin_start(12)
        self._meta_group.set_margin_end(12)
        self._meta_group.set_margin_top(12)
        self._path_row = Adw.ActionRow(title="Path")
        self._sessions_row = Adw.ActionRow(title="Sessions")
        self._active_row = Adw.ActionRow(title="Last active")
        for row in (self._path_row, self._sessions_row, self._active_row):
            self._meta_group.add(row)
        self.append(self._meta_group)

        # ViewStack for agent tabs
        self._stack = Adw.ViewStack()
        self._stack.set_vexpand(True)
        self.append(self._stack)

        # ViewSwitcherBar at bottom
        self._switcher = Adw.ViewSwitcherBar()
        self._switcher.set_stack(self._stack)
        self._switcher.set_reveal(True)
        self.append(self._switcher)

    def load(self, project: ProjectInfo) -> None:
        self._project = project

        # Update metadata
        path_sub = project.original_path
        if not project.exists_on_disk:
            path_sub += "  (directory not found)"
        self._path_row.set_subtitle(path_sub)
        self._sessions_row.set_subtitle(str(len(project.sessions)))
        la = project.last_active
        self._active_row.set_subtitle(
            la.strftime("%Y-%m-%d %H:%M") if la.year > 1 else "—"
        )

        # Discover agent configs
        from hub.data.agent_config import discover_agent_configs
        configs = discover_agent_configs(project.original_path, project.sessions)

        # Clear existing tabs
        while True:
            page = self._stack.get_first_child()
            if page is None:
                break
            self._stack.remove(page)
        self._tabs.clear()

        # Build tabs for agents with data
        for config in configs:
            if not config.has_data:
                continue

            if config.agent == "claude":
                from hub.ui.claude_tab import ClaudeTab
                tab = ClaudeTab()
                tab.load(project.original_path, config)
                self._stack.add_titled_with_icon(tab, "claude", "Claude", "document-edit-symbolic")

            elif config.agent == "codex":
                from hub.ui.codex_tab import CodexTab
                tab = CodexTab()
                tab.load(project.original_path, config)
                self._stack.add_titled_with_icon(tab, "codex", "Codex", "utilities-terminal-symbolic")

            elif config.agent == "antigravity":
                from hub.ui.antigravity_tab import AntiGravityTab
                tab = AntiGravityTab()
                tab.load(config)
                self._stack.add_titled_with_icon(tab, "antigravity", "Anti-Gravity", "weather-clear-symbolic")

            self._tabs[config.agent] = tab

        # Hide switcher if only one tab
        self._switcher.set_reveal(len(self._tabs) > 1)
```

- [ ] **Step 2: Verify the app loads**

Run: `./run-dev.sh` — click a project, verify tabs appear.

- [ ] **Step 3: Commit**

```bash
git add hub/ui/project_viewer.py
git commit -m "refactor(ui): project viewer as ViewStack orchestrator with multi-agent tabs"
```

---

### Task 6: Integration Smoke Test

- [ ] **Step 1: Run full test suite**

Run: `GSETTINGS_BACKEND=memory pytest tests/ -v`

- [ ] **Step 2: Manual UI verification**

Launch `./run-dev.sh` and verify:
- Click a project with Claude sessions → Claude tab appears with CLAUDE.md chain + Memory section
- Memory entries show with name, description, type badge
- Click a memory → edit dialog opens, save works, file updated on disk
- If project has Codex sessions → Codex tab appears
- If project has AG sessions → Anti-Gravity tab appears with GEMINI.md + banner
- ViewSwitcherBar shows at bottom when multiple tabs present
- ViewSwitcherBar hidden when only one tab

- [ ] **Step 3: Commit any fixes**

```bash
git commit -m "fix: integration adjustments from agent config editor smoke testing"
```
