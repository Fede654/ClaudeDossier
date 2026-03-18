# Full Item Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ClaudeDossier render all content from all three agent sources — Claude tool_use/thinking blocks, Codex SQLite metadata, and Anti-Gravity brain/ plaintext markdown.

**Architecture:** Three independent improvements to the data layer (scanner + parser), each behind the existing GSettings agent toggle. No UI changes needed — the session viewer already renders whatever ParsedMessage list the parser returns.

**Tech Stack:** Python 3.10+, SQLite3 (stdlib), pathlib, pytest

**Pre-existing bug:** `session_parser.py` line 120 uses `timezone` but only imports `datetime` from the `datetime` module. Fix this in Task 1 by adding `timezone` to the import.

**Intentional behavior change:** The new `_text()` joins content blocks with `"\n\n"` instead of `""`. Multi-block messages will have paragraph breaks between blocks. Existing tests use `in` assertions and will pass. This is desirable — it separates tool calls from prose visually.

---

## File Structure

| File | Responsibility | Tasks |
|------|---------------|-------|
| `hub/data/session_parser.py` | Parse content blocks including tool_use/thinking | Task 1 |
| `hub/data/session_scanner.py` | Codex SQLite scanner, AG brain/ scanner | Tasks 2, 3 |
| `hub/data/codex_sqlite.py` | **CREATE** — Read Codex state_5.sqlite threads table | Task 2 |
| `hub/data/antigravity_brain.py` | **CREATE** — Read AG brain/ markdown files | Task 3 |
| `tests/test_session_parser.py` | New tests for tool_use/thinking content blocks | Task 1 |
| `tests/test_codex_sqlite.py` | **CREATE** — Tests for Codex SQLite reader | Task 2 |
| `tests/test_antigravity_brain.py` | **CREATE** — Tests for AG brain/ reader | Task 3 |

---

### Task 1: Claude Content Block Coverage

**Context:** `_text()` at `hub/data/session_parser.py:38-43` extracts only `b.get("text", "")` from content blocks. This silently drops `tool_use` (has `name`/`input`), `tool_result` (has `content`), and `thinking` (has `thinking` field) blocks. Users see incomplete conversations.

**Files:**
- Modify: `hub/data/session_parser.py:38-43` (`_text()` function)
- Test: `tests/test_session_parser.py`

- [ ] **Step 1: Write failing test for tool_use blocks**

```python
def test_content_includes_tool_use(tmp_path):
    from hub.data.session_parser import SessionParser
    msg = {"type": "assistant", "uuid": "a1",
           "timestamp": "2026-01-01T10:00:00.000Z",
           "message": {"role": "assistant", "content": [
               {"type": "text", "text": "Let me read that file."},
               {"type": "tool_use", "id": "toolu_123", "name": "Read",
                "input": {"file_path": "/tmp/foo.py"}},
           ]}}
    result = SessionParser().parse(_jsonl(tmp_path, [msg]))
    assert "Read" in result[0].text
    assert "/tmp/foo.py" in result[0].text
```

- [ ] **Step 2: Write failing test for tool_result blocks**

```python
def test_content_includes_tool_result(tmp_path):
    from hub.data.session_parser import SessionParser
    msg = {"type": "assistant", "uuid": "a1",
           "timestamp": "2026-01-01T10:00:00.000Z",
           "message": {"role": "assistant", "content": [
               {"type": "tool_result", "tool_use_id": "toolu_123",
                "content": "file contents here"},
           ]}}
    result = SessionParser().parse(_jsonl(tmp_path, [msg]))
    assert "file contents here" in result[0].text
```

- [ ] **Step 3: Write failing test for thinking blocks**

```python
def test_content_includes_thinking(tmp_path):
    from hub.data.session_parser import SessionParser
    msg = {"type": "assistant", "uuid": "a1",
           "timestamp": "2026-01-01T10:00:00.000Z",
           "message": {"role": "assistant", "content": [
               {"type": "thinking", "thinking": "I need to consider the edge cases..."},
               {"type": "text", "text": "Here is my answer."},
           ]}}
    result = SessionParser(include_progress=True).parse(_jsonl(tmp_path, [msg]))
    assert "I need to consider" in result[0].text
    assert "Here is my answer" in result[0].text
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `GSETTINGS_BACKEND=memory pytest tests/test_session_parser.py -v -k "tool_use or tool_result or thinking"`
Expected: 3 FAIL

- [ ] **Step 5: Fix missing `timezone` import and implement `_text()` upgrade**

First, fix the import at line 7 of `hub/data/session_parser.py`:
```python
from datetime import datetime, timezone
```

Then replace `_text()` at lines 38-43 with:

```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `GSETTINGS_BACKEND=memory pytest tests/test_session_parser.py -v`
Expected: ALL PASS (including existing tests — `_text()` is backwards-compatible for `text` blocks)

- [ ] **Step 7: Commit**

```bash
git add hub/data/session_parser.py tests/test_session_parser.py
git commit -m "feat(parser): render tool_use, tool_result, and thinking content blocks"
```

---

### Task 2: Codex SQLite Thread Metadata

**Context:** Codex CLI's `state_5.sqlite` has 313 non-archived threads with titles, CWD, git branch, git SHA, timestamps, and `first_user_message`. The current CodexScanner only reads JSONL files and misses this richer metadata. This task adds a SQLite reader that enriches existing JSONL-based sessions and surfaces threads that have no JSONL at all.

**Schema** (from `~/.codex/state_5.sqlite`):
```sql
CREATE TABLE threads (
    id TEXT PRIMARY KEY,
    rollout_path TEXT NOT NULL,
    created_at INTEGER NOT NULL,  -- Unix epoch
    updated_at INTEGER NOT NULL,
    cwd TEXT NOT NULL,
    title TEXT NOT NULL,
    git_sha TEXT,
    git_branch TEXT,
    git_origin_url TEXT,
    first_user_message TEXT NOT NULL DEFAULT '',
    tokens_used INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0
    -- plus: source, model_provider, sandbox_policy, approval_mode, cli_version, etc.
);
```

**Files:**
- Create: `hub/data/codex_sqlite.py`
- Modify: `hub/data/session_scanner.py:157-243` (CodexScanner)
- Create: `tests/test_codex_sqlite.py`

- [ ] **Step 1: Write failing test for codex_sqlite reader**

Create `tests/test_codex_sqlite.py`:

```python
import sqlite3
from pathlib import Path


def _make_db(tmp_path, threads):
    """Create a minimal state_5.sqlite with threads table."""
    db = tmp_path / "state_5.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("""CREATE TABLE threads (
        id TEXT PRIMARY KEY,
        rollout_path TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        source TEXT NOT NULL DEFAULT 'cli',
        model_provider TEXT NOT NULL DEFAULT 'openai',
        cwd TEXT NOT NULL,
        title TEXT NOT NULL,
        sandbox_policy TEXT NOT NULL DEFAULT 'locked',
        approval_mode TEXT NOT NULL DEFAULT 'suggest',
        tokens_used INTEGER NOT NULL DEFAULT 0,
        has_user_event INTEGER NOT NULL DEFAULT 0,
        archived INTEGER NOT NULL DEFAULT 0,
        archived_at INTEGER,
        git_sha TEXT,
        git_branch TEXT,
        git_origin_url TEXT,
        cli_version TEXT NOT NULL DEFAULT '',
        first_user_message TEXT NOT NULL DEFAULT '',
        agent_nickname TEXT,
        agent_role TEXT,
        memory_mode TEXT NOT NULL DEFAULT 'enabled'
    )""")
    for t in threads:
        conn.execute(
            "INSERT INTO threads (id, rollout_path, created_at, updated_at, cwd, title, git_branch, first_user_message, archived) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (t["id"], t.get("rollout_path", ""), t["created_at"], t["updated_at"],
             t["cwd"], t["title"], t.get("git_branch", ""), t.get("first_user_message", ""), t.get("archived", 0)),
        )
    conn.commit()
    conn.close()
    return db


def test_loads_non_archived_threads(tmp_path):
    from hub.data.codex_sqlite import load_codex_threads
    _make_db(tmp_path, [
        {"id": "t1", "created_at": 1710000000, "updated_at": 1710000100,
         "cwd": "/home/user/project", "title": "Fix bug", "git_branch": "main",
         "first_user_message": "fix the login bug"},
        {"id": "t2", "created_at": 1710000200, "updated_at": 1710000300,
         "cwd": "/home/user/project", "title": "Archived", "archived": 1},
    ])
    threads = load_codex_threads(tmp_path / "state_5.sqlite")
    assert len(threads) == 1
    assert threads[0]["id"] == "t1"
    assert threads[0]["title"] == "Fix bug"
    assert threads[0]["git_branch"] == "main"
    assert threads[0]["first_user_message"] == "fix the login bug"


def test_returns_empty_for_missing_db(tmp_path):
    from hub.data.codex_sqlite import load_codex_threads
    assert load_codex_threads(tmp_path / "nonexistent.sqlite") == []


def test_groups_by_cwd(tmp_path):
    from hub.data.codex_sqlite import load_codex_threads
    _make_db(tmp_path, [
        {"id": "t1", "created_at": 1710000000, "updated_at": 1710000100,
         "cwd": "/proj/a", "title": "Task A"},
        {"id": "t2", "created_at": 1710000200, "updated_at": 1710000300,
         "cwd": "/proj/b", "title": "Task B"},
    ])
    threads = load_codex_threads(tmp_path / "state_5.sqlite")
    cwds = {t["cwd"] for t in threads}
    assert cwds == {"/proj/a", "/proj/b"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `GSETTINGS_BACKEND=memory pytest tests/test_codex_sqlite.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement codex_sqlite.py**

Create `hub/data/codex_sqlite.py`:

```python
"""Reads Codex CLI thread metadata from state_5.sqlite."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path.home() / ".codex" / "state_5.sqlite"

_QUERY = """
SELECT id, rollout_path, created_at, updated_at, cwd, title,
       git_branch, git_sha, first_user_message, tokens_used
FROM threads
WHERE archived = 0
ORDER BY updated_at DESC
"""


def load_codex_threads(db_path: Path | None = None) -> list[dict]:
    """Return a list of non-archived thread dicts from Codex state_5.sqlite."""
    path = db_path or _DEFAULT_DB
    if not path.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(_QUERY).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Cannot read Codex SQLite %s: %s", path, e)
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `GSETTINGS_BACKEND=memory pytest tests/test_codex_sqlite.py -v`
Expected: ALL PASS

- [ ] **Step 5: Write failing test for CodexScanner SQLite enrichment**

Add to `tests/test_session_scanner.py` (or create a new `tests/test_codex_scanner.py`):

```python
import json
import sqlite3
from pathlib import Path


def test_codex_scanner_includes_sqlite_threads(tmp_path):
    from hub.data.session_scanner import CodexScanner

    # Create sessions dir with one JSONL
    sessions_dir = tmp_path / "sessions" / "2026" / "03" / "18"
    sessions_dir.mkdir(parents=True)
    jsonl = sessions_dir / "rollout-abc.jsonl"
    jsonl.write_text(json.dumps({
        "type": "response_item",
        "payload": {"type": "message", "role": "user",
                    "content": [{"type": "input_text", "text": "<cwd>/proj</cwd>\nhello"}]}
    }))

    # Create SQLite with a thread that has NO matching JSONL
    db = tmp_path / "state_5.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("""CREATE TABLE threads (
        id TEXT PRIMARY KEY, rollout_path TEXT NOT NULL,
        created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
        source TEXT NOT NULL DEFAULT 'cli', model_provider TEXT NOT NULL DEFAULT 'openai',
        cwd TEXT NOT NULL, title TEXT NOT NULL,
        sandbox_policy TEXT NOT NULL DEFAULT 'locked', approval_mode TEXT NOT NULL DEFAULT 'suggest',
        tokens_used INTEGER NOT NULL DEFAULT 0, has_user_event INTEGER NOT NULL DEFAULT 0,
        archived INTEGER NOT NULL DEFAULT 0, archived_at INTEGER,
        git_sha TEXT, git_branch TEXT, git_origin_url TEXT,
        cli_version TEXT NOT NULL DEFAULT '', first_user_message TEXT NOT NULL DEFAULT '',
        agent_nickname TEXT, agent_role TEXT, memory_mode TEXT NOT NULL DEFAULT 'enabled'
    )""")
    conn.execute(
        "INSERT INTO threads (id, rollout_path, created_at, updated_at, cwd, title, git_branch, first_user_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("sqlite-only-thread", "", 1710000000, 1710000100, "/proj/sqlite", "SQLite Thread", "feat/x", "do the thing"),
    )
    conn.commit()
    conn.close()

    scanner = CodexScanner(codex_root=tmp_path / "sessions", sqlite_path=db)
    projects = scanner.scan()

    # Should have both the JSONL project and the SQLite-only project
    all_sessions = [s for p in projects for s in p.sessions]
    ids = {s.session_id for s in all_sessions}
    assert "sqlite-only-thread" in ids

    sqlite_session = next(s for s in all_sessions if s.session_id == "sqlite-only-thread")
    assert sqlite_session.first_prompt == "do the thing"
    assert sqlite_session.git_branch == "feat/x"
```

- [ ] **Step 6: Run test to verify it fails**

Run: `GSETTINGS_BACKEND=memory pytest tests/test_codex_scanner.py -v`
Expected: FAIL

- [ ] **Step 7: Integrate SQLite into CodexScanner**

Modify `hub/data/session_scanner.py`:

**Step 7a:** Change `CodexScanner.__init__()` (line 158) to accept `sqlite_path`:
```python
class CodexScanner:
    def __init__(self, codex_root: Path | None = None, sqlite_path: Path | None = None):
        self.codex_root = codex_root or Path.home() / ".codex" / "sessions"
        self.sqlite_path = sqlite_path or Path.home() / ".codex" / "state_5.sqlite"
```

**Step 7b:** Insert the following SQLite enrichment block at line 243 (AFTER the existing `for jsonl in self.codex_root.rglob(...)` loop, BEFORE the `return list(project_map.values())`):
```python
        # --- SQLite enrichment (insert before return) ---
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
```

**Step 7c:** Update `SessionScanner.__init__` (line 281) to pass `sqlite_path` through:
```python
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
```
When `projects_root` is set (test mode), `codex_sqlite_path` defaults to `None` which means `CodexScanner` will use its own default. In tests, pass it explicitly.

- [ ] **Step 8: Run all tests**

Run: `GSETTINGS_BACKEND=memory pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add hub/data/codex_sqlite.py hub/data/session_scanner.py tests/test_codex_sqlite.py tests/test_codex_scanner.py
git commit -m "feat(codex): read state_5.sqlite for thread metadata and SQLite-only sessions"
```

---

### Task 3: Anti-Gravity Brain Directory

**Context:** Anti-Gravity stores plaintext markdown in `~/.gemini/antigravity/brain/{conversation-id}/` with files like `task.md`, `implementation_plan.md`, `walkthrough.md`. 9 conversations available, completely untapped. This is the highest-value data source — rich, structured, trivial to parse.

**Brain directory structure** (per conversation):
```
{conversation-id}/
├── task.md                          # Task description
├── implementation_plan.md           # AI implementation plan
├── walkthrough.md                   # Code walkthrough
├── *.metadata.json                  # Artifact metadata
├── *.resolved                       # Version history
└── ia_exchange_protocol.md          # (varies by conversation)
```

**Files:**
- Create: `hub/data/antigravity_brain.py`
- Modify: `hub/data/session_scanner.py:246-277` (AntiGravityScanner)
- Modify: `hub/data/session_parser.py:156-231` (AntiGravityParser)
- Create: `tests/test_antigravity_brain.py`

- [ ] **Step 1: Write failing test for brain reader**

Create `tests/test_antigravity_brain.py`:

```python
from pathlib import Path


def _make_brain(tmp_path, conv_id, files):
    """Create a brain directory with the given markdown files."""
    brain_dir = tmp_path / "brain" / conv_id
    brain_dir.mkdir(parents=True)
    for name, content in files.items():
        (brain_dir / name).write_text(content)
    return brain_dir


def test_reads_brain_markdown(tmp_path):
    from hub.data.antigravity_brain import load_brain
    _make_brain(tmp_path, "abc-123", {
        "task.md": "# Fix the login flow\nUsers can't log in after password reset.",
        "implementation_plan.md": "## Plan\n1. Check auth middleware\n2. Fix token refresh",
        "walkthrough.md": "## Walkthrough\nThe auth module handles...",
    })
    result = load_brain(tmp_path / "brain" / "abc-123")
    assert "Fix the login flow" in result["task"]
    assert "Check auth middleware" in result["implementation_plan"]
    assert "auth module" in result["walkthrough"]


def test_handles_missing_files(tmp_path):
    from hub.data.antigravity_brain import load_brain
    _make_brain(tmp_path, "abc-123", {"task.md": "# Just a task"})
    result = load_brain(tmp_path / "brain" / "abc-123")
    assert "Just a task" in result["task"]
    assert result["implementation_plan"] == ""
    assert result["walkthrough"] == ""


def test_returns_empty_for_missing_dir(tmp_path):
    from hub.data.antigravity_brain import load_brain
    result = load_brain(tmp_path / "brain" / "nonexistent")
    assert result["task"] == ""


def test_lists_brain_conversations(tmp_path):
    from hub.data.antigravity_brain import list_brain_conversations
    brain_root = tmp_path / "brain"
    brain_root.mkdir()
    (brain_root / "conv-1").mkdir()
    (brain_root / "conv-1" / "task.md").write_text("Task 1")
    (brain_root / "conv-2").mkdir()
    (brain_root / "conv-2" / "task.md").write_text("Task 2")
    (brain_root / "not-a-dir.txt").write_text("ignore")
    convs = list_brain_conversations(brain_root)
    assert set(convs) == {"conv-1", "conv-2"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `GSETTINGS_BACKEND=memory pytest tests/test_antigravity_brain.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement antigravity_brain.py**

Create `hub/data/antigravity_brain.py`:

```python
"""Reads Anti-Gravity brain/ directory — plaintext markdown per conversation."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_BRAIN_ROOT = Path.home() / ".gemini" / "antigravity" / "brain"

_KNOWN_FILES = ("task.md", "implementation_plan.md", "walkthrough.md")


def load_brain(conv_dir: Path) -> dict[str, str]:
    """Read markdown files from a single conversation's brain directory.

    Returns a dict with keys 'task', 'implementation_plan', 'walkthrough'
    (empty string if file is missing).
    """
    result = {}
    for fname in _KNOWN_FILES:
        key = fname.removesuffix(".md")
        path = conv_dir / fname
        try:
            result[key] = path.read_text(encoding="utf-8") if path.exists() else ""
        except OSError as e:
            logger.warning("Cannot read %s: %s", path, e)
            result[key] = ""
    return result


def list_brain_conversations(brain_root: Path | None = None) -> list[str]:
    """Return conversation IDs (directory names) that have brain data."""
    root = brain_root or _DEFAULT_BRAIN_ROOT
    if not root.exists():
        return []
    return [d.name for d in sorted(root.iterdir()) if d.is_dir()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `GSETTINGS_BACKEND=memory pytest tests/test_antigravity_brain.py -v`
Expected: ALL PASS

- [ ] **Step 5: Write failing test for AntiGravityScanner brain integration**

Add to `tests/test_antigravity_brain.py`:

```python
def test_scanner_includes_brain_sessions(tmp_path):
    from hub.data.session_scanner import AntiGravityScanner

    # Create conversations/ with one .pb file
    convs = tmp_path / "conversations"
    convs.mkdir()
    (convs / "conv-1.pb").write_bytes(b"\x00" * 100)

    # Create brain/ with a conversation that has NO .pb file
    brain = tmp_path / "brain"
    brain.mkdir()
    brain_conv = brain / "conv-brain-only"
    brain_conv.mkdir()
    (brain_conv / "task.md").write_text("# Brain-only task\nThis has no .pb file.")

    scanner = AntiGravityScanner(root=convs, brain_root=brain)
    projects = scanner.scan()
    all_sessions = [s for p in projects for s in p.sessions]
    ids = {s.session_id for s in all_sessions}

    assert "conv-1" in ids          # from .pb
    assert "conv-brain-only" in ids  # from brain/
```

- [ ] **Step 6: Run test to verify it fails**

Run: `GSETTINGS_BACKEND=memory pytest tests/test_antigravity_brain.py::test_scanner_includes_brain_sessions -v`
Expected: FAIL

- [ ] **Step 7: Integrate brain/ into AntiGravityScanner**

Modify `hub/data/session_scanner.py` — rewrite `AntiGravityScanner` to handle both .pb files AND brain-only conversations.

**Key change:** Create the `project` object unconditionally at the top of `scan()`, so it exists for brain-only conversations even when `self.root` doesn't exist.

```python
class AntiGravityScanner:
    def __init__(self, root: Path | None = None, brain_root: Path | None = None):
        self.root = root or Path.home() / ".gemini" / "antigravity" / "conversations"
        self.brain_root = brain_root or Path.home() / ".gemini" / "antigravity" / "brain"

    def scan(self) -> list[ProjectInfo]:
        project = ProjectInfo(original_path=str(self.root), project_dir=self.root)

        # --- .pb file scan (existing logic, unchanged) ---
        if self.root.exists():
            for pbfile in self.root.glob("*.pb"):
                try:
                    fallback = datetime.fromtimestamp(pbfile.stat().st_mtime, tz=timezone.utc)
                except OSError:
                    fallback = datetime.now(tz=timezone.utc)
                info = SessionInfo(
                    session_id=pbfile.stem,
                    first_prompt=f"Anti-Gravity Session {pbfile.stem}",
                    message_count=1,
                    created=fallback,
                    modified=fallback,
                    git_branch="",
                    project_path=str(self.root),
                    is_sidechain=False,
                    jsonl_path=pbfile,
                    agent_source="antigravity"
                )
                project.sessions.append(info)

        # --- brain/ directory scan (NEW) ---
        from hub.data.antigravity_brain import list_brain_conversations
        seen_ids = {s.session_id for s in project.sessions}

        for conv_id in list_brain_conversations(self.brain_root):
            if conv_id in seen_ids:
                continue  # already have this from .pb
            try:
                brain_dir = self.brain_root / conv_id
                fallback = datetime.fromtimestamp(brain_dir.stat().st_mtime, tz=timezone.utc)
            except OSError:
                fallback = datetime.now(tz=timezone.utc)
            info = SessionInfo(
                session_id=conv_id,
                first_prompt=f"Anti-Gravity Brain: {conv_id}",
                message_count=1,
                created=fallback,
                modified=fallback,
                git_branch="",
                project_path=str(self.root),
                is_sidechain=False,
                jsonl_path=brain_dir,  # points to brain dir; parser detects via is_dir()
                agent_source="antigravity",
            )
            project.sessions.append(info)

        return [project] if project.sessions else []
```

**Step 7b:** Update `SessionScanner.__init__` (line 281) to pass `brain_root`:
```python
class SessionScanner:
    def __init__(self, projects_root: Path | None = None, codex_root: Path | None = None,
                 antigravity_root: Path | None = None, codex_sqlite_path: Path | None = None,
                 antigravity_brain_root: Path | None = None):
        self.claude = ClaudeScanner(projects_root)
        if projects_root is not None and codex_root is None:
            codex_root = projects_root / ".codex_fake"
        if projects_root is not None and antigravity_root is None:
            antigravity_root = projects_root / ".ag_fake"
        self.codex = CodexScanner(codex_root, sqlite_path=codex_sqlite_path)
        self.antigravity = AntiGravityScanner(antigravity_root, brain_root=antigravity_brain_root)
```

- [ ] **Step 8: Integrate brain/ into AntiGravityParser**

Modify `hub/data/session_parser.py` AntiGravityParser.parse() — restructure to handle brain-only sessions (where `path` is a directory, not a .pb file).

**Key insight:** For brain-only sessions, the scanner sets `jsonl_path` to the brain directory itself. When `path.is_dir()` is True, we should read brain content and skip the vscdb/opaque-placeholder logic entirely.

Replace the entire `parse()` method body:

```python
    def parse(self, path: Path) -> list[ParsedMessage]:
        results = []
        conv_id = path.stem  # works for both files (.pb stem) and dirs (dir name)

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

        # .pb file session: existing vscdb logic (unchanged)
        try:
            trajectories = self._trajectories()
            info = trajectories.get(conv_id)

            if info:
                # ... existing title + turns logic (unchanged) ...
                pass
            else:
                # ... existing "Opaque" fallback (unchanged) ...
                pass
        except Exception as e:
            # ... existing error handling (unchanged) ...
            pass

        # Also check brain/ for this conversation (may have both .pb and brain/)
        from hub.data.antigravity_brain import load_brain
        brain_dir = Path.home() / ".gemini" / "antigravity" / "brain" / conv_id
        if brain_dir.is_dir():
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
```

**Important:** The `# ... existing logic (unchanged)` comments mean keep the current code in those branches. The only structural change is: (1) early-return for `path.is_dir()` brain-only sessions, (2) brain/ append after the existing try/except for .pb sessions.

- [ ] **Step 9: Run all tests**

Run: `GSETTINGS_BACKEND=memory pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 10: Commit**

```bash
git add hub/data/antigravity_brain.py hub/data/session_scanner.py hub/data/session_parser.py tests/test_antigravity_brain.py
git commit -m "feat(antigravity): read brain/ directory for plaintext task, plan, and walkthrough markdown"
```

---

### Task 4: Final Integration Smoke Test

- [ ] **Step 1: Run full test suite**

Run: `GSETTINGS_BACKEND=memory pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: Manual smoke test**

Run: `./run-dev.sh`
Verify:
- Claude sessions show tool_use blocks as formatted code blocks (not blank gaps)
- Codex sidebar shows titles from SQLite (not just "Codex Session rollout-xxx")
- Anti-Gravity sidebar shows brain-only conversations
- Anti-Gravity session view shows Task/Plan/Walkthrough sections

- [ ] **Step 3: Final commit if any adjustments needed**

```bash
git commit -m "fix: integration adjustments from smoke testing"
```
