# Conversation Archive Design

## Problem

ClaudeDossier reads AI conversation history from three sources that actively destroy data:

- **Claude Code**: Rotates/deletes JSONL files (100% loss rate on indexed sessions)
- **Codex CLI**: `state_5.sqlite` (12.7GB) has no backup mechanism; JSONL files may be cleaned
- **Anti-Gravity**: `.pb` files encrypted with inaccessible keys; `brain/` and `state.vscdb` persistence unknown

Dossier currently reads on demand and stores nothing. It's a viewer into disappearing data. The app needs to become the canonical store — source files are import feeds, Dossier's archive is the truth.

## Design

### Core Idea

An append-only mirror at `~/.local/share/claude-dossier/archive/`. On startup and manual refresh, new/changed text files are synced from source into the mirror using safe-copy semantics. Binary files (SQLite databases) are snapshot-copied via the SQLite backup API into a separate `snapshots/` directory. Scanners read from the mirror. Source files can disappear — the mirror keeps everything.

No git. Preservation does not require versioning. A JSON-lines sync log provides auditability.

### Directory Layout

```
~/.local/share/claude-dossier/
├── archive/                              # Canonical text store
│   ├── claude/projects/                  # Mirror of ~/.claude/projects/
│   │   └── <url-encoded-path>/
│   │       ├── sessions-index.json       # Metadata (titles, branches)
│   │       └── *.jsonl                   # Conversation transcripts
│   ├── codex/sessions/                   # Mirror of ~/.codex/sessions/
│   │   └── YYYY/MM/DD/rollout-*.jsonl
│   └── antigravity/brain/                # Mirror of ~/.gemini/antigravity/brain/
│       └── <conversation-id>/
│           ├── task.md
│           ├── implementation_plan.md
│           └── walkthrough.md
├── snapshots/                            # Binary files (outside archive)
│   ├── codex_state_5.sqlite              # sqlite3.backup() snapshot
│   └── antigravity_state.vscdb           # sqlite3.backup() snapshot
├── sync.log                              # JSONL audit trail
└── .sync.lock                            # flock for single-writer
```

**What is NOT archived:**
- Anti-Gravity `.pb` files — encrypted, unreadable, pure disk waste until keys become accessible
- FTS search index — stays at `~/.cache/claude-dossier/search.db` (rebuildable, XDG-correct)

### Sync Logic

Sync runs on **startup** and on **manual refresh** (user-triggered). It runs in a background thread with progress callbacks to the UI.

#### 1. Single-Writer Lock

Acquire `flock` on `~/.local/share/claude-dossier/.sync.lock` before any I/O. If another sync is running (another app window, or startup overlapping with refresh), wait with backoff or skip with a warning. No concurrent syncs.

#### 2. Text File Sync (JSONL, Markdown, JSON, sessions-index.json)

For each source directory, walk all text files (`.jsonl`, `.json`, `.md`). This explicitly includes `sessions-index.json` (Claude metadata: titles, branches, prompt previews — not present in JSONL itself). For each file:

**New file** (exists in source, not in mirror): Copy to mirror using atomic temp+rename.

**Existing file — source grew** (append detection): Compare first 4KB hash of source vs mirror. If identical prefix → source was appended to → tail-safe copy: read source from mirror's byte offset to EOF, append to mirror, truncate at last complete newline.

**Existing file — source diverged** (rotation detection): First 4KB hash differs → source was rotated/replaced. Keep the existing mirror file (rename to `<name>.pre-rotation-<timestamp>`), copy the new source content as the primary file. Both versions preserved.

**Source file gone** (deleted/rotated away): Mirror keeps it. No action. These are "mirror-only" sessions.

**Tail-safe copy**: Always copy up to the last complete newline (`\n`). If the last byte isn't `\n`, truncate to the previous one. This prevents capturing partial JSON lines from in-progress writes. Note: if a writer is mid-line, the truncation may discard content that only appears on the next sync. **Session content is eventually consistent, not immediately consistent.**

**Atomic writes**: All copies go to a temp file in the same directory, then `os.rename()` (atomic on Linux).

**Hashing**: All content hashes use SHA-256. The `sha256_4k` field in sync.log is SHA-256 of the first 4096 bytes.

#### 3. SQLite Snapshots

For each SQLite source (`~/.codex/state_5.sqlite`, `~/.config/Antigravity/User/globalStorage/state.vscdb`):

1. Check source `mtime` against last snapshot `mtime` (stored in sync.log). If unchanged, skip.
2. Use `sqlite3.backup()` API (handles WAL/journal correctly, safe against concurrent writers).
3. Write to temp file, verify with `PRAGMA integrity_check`, then atomic rename to final path.

**Important**: `sqlite3.backup()` copies the entire database in a single call by default — it is NOT incremental across calls. For a 12.7GB file, the first backup will take minutes. The mtime gate ensures this only happens when the source actually changed, not on every sync. Expect the first-ever sync to be slow; subsequent syncs skip unless Codex has written new data.

#### 4. Sync Log

After each sync operation, append a JSONL entry to `sync.log`:

```json
{"ts": "2026-03-18T10:00:00Z", "action": "copy", "source": "~/.claude/projects/.../abc.jsonl", "dest": "archive/claude/projects/.../abc.jsonl", "bytes": 45023, "sha256_4k": "a1b2c3..."}
{"ts": "2026-03-18T10:00:00Z", "action": "rotation_detected", "source": "~/.claude/projects/.../def.jsonl", "preserved_as": "def.pre-rotation-20260318T100000.jsonl", "new_bytes": 12045}
{"ts": "2026-03-18T10:00:01Z", "action": "sqlite_backup", "source": "~/.codex/state_5.sqlite", "dest": "snapshots/codex_state_5.sqlite", "pages": 810234}
{"ts": "2026-03-18T10:00:01Z", "action": "skip", "source": "~/.codex/state_5.sqlite", "reason": "mtime_unchanged"}
```

### Scanner Integration

#### SessionInfo Changes

Add two fields to the `SessionInfo` dataclass:

```python
@dataclass
class SessionInfo:
    # ... existing fields ...
    jsonl_path: Path              # Best-available path (archive or source) — parsers read this
    source_path: Path | None = None    # Original location (provenance, shown in UI)
    archive_path: Path | None = None   # Mirror location (set by archive layer)
```

**Path resolution is done at scan time, not at access time.** There is no dynamic alias or `@property`. The scanner sets `jsonl_path` to the best-available path when constructing each `SessionInfo`:

```python
# In each scanner, after constructing SessionInfo:
if archive_file.exists():
    info.archive_path = archive_file
    info.jsonl_path = archive_file     # parsers read from archive
else:
    info.jsonl_path = source_file      # fallback to source
info.source_path = source_file         # always set for provenance
```

This means:
- `jsonl_path` remains a plain `Path` field — no property magic, no dataclass hacks
- All existing code (`parser.parse(session.jsonl_path)`, `search_index`, UI) works unchanged
- `source_path` is available for UI display ("where this session came from")
- `archive_path` is available for sync logic ("where the mirror copy is")

**Special cases:**
- **SQLite-only Codex sessions** (no JSONL file): `source_path = None`, `archive_path = None`, `jsonl_path = Path("")` (empty, as currently). These sessions surface metadata from SQLite only — no file to parse.
- **Brain-only Anti-Gravity sessions**: `jsonl_path` points to the brain directory (archive copy). The `path.is_dir()` check in `AntiGravityParser` works the same way.

#### Scanner Path Resolution

`SessionScanner.__init__` gains an `archive_root` parameter:

```python
def __init__(self, archive_root: Path | None = None, ...):
    self.archive_root = archive_root or Path.home() / ".local/share/claude-dossier"
```

Each sub-scanner reads from `archive_root/archive/<agent>/...` if it exists, otherwise falls back to the source path. This means:
- First run (no archive yet): reads from source as before
- Subsequent runs: reads from mirror
- Archive disabled/broken: graceful fallback to source

#### Parser Changes

Parsers receive a `Path` via `jsonl_path` and read it. They don't care whether it points to source or mirror — with one exception:

**Required fix — AntiGravityParser hardcoded brain path**: At `session_parser.py:275`, the parser independently constructs a brain directory path:
```python
brain_dir = Path.home() / ".gemini" / "antigravity" / "brain" / conv_id
```
This bypasses the archive. Fix: look for brain content relative to the archive first. The parser should check the archive brain path (derivable from `jsonl_path`'s parent structure) before falling back to the hardcoded source path.

#### Search Index Consideration

`search_index.py` uses `session.jsonl_path.stat().st_mtime` for mtime gating. When `jsonl_path` points to an archive file, the mtime reflects the sync timestamp, not the source write time. This means sessions may be re-indexed after each sync even if content didn't change. Mitigation: the search index already checks content via FTS rowcount — re-indexing an unchanged file is a no-op in practice. If this becomes a performance issue, add a content hash check to the index.

### UI Integration

#### Startup Flow

```
Application starts
  → Acquire .sync.lock (non-blocking attempt)
  → If acquired: run sync in background thread
    → Progress: "Syncing conversations... (N files)"
    → On completion: release lock, run scanners, populate UI
  → If lock busy: skip sync, run scanners on existing archive
    → Show: "Archive sync in progress in another window"
```

#### Refresh Flow

Same as startup sync, triggered by the refresh button/signal.

#### Mirror-Only Sessions

Sessions that exist in the archive but not in the source get a visual indicator (e.g., dimmed icon or "(archived)" suffix). The "Resume" action is disabled for these — the source session no longer exists.

#### First-Run UX

On first launch (no archive exists yet), sync must complete before scanners have anything to read. The UI shows a progress indicator during this initial sync. On subsequent launches, the existing archive is populated instantly while sync runs in the background to pick up changes.

### Error Handling

| Failure | Behavior |
|---------|----------|
| Lock busy | Skip sync, read existing archive, show info message |
| Source file unreadable (permissions) | Log warning, skip file, continue sync |
| Partial JSONL write (torn read) | Truncate at last complete newline |
| SQLite backup fails | Log warning, keep previous snapshot, continue |
| Archive directory doesn't exist | Create it on first sync |
| Archive disk full | Abort sync, show error, fall back to source paths |
| Corrupt archive file | Parser error handling unchanged (already graceful) |

### Testing Strategy

1. **Unit tests for sync logic**: temp directory fixtures with fake JSONL/SQLite sources. Test: new file copy, append detection, rotation detection, tail truncation, mtime gating.
2. **SQLite backup test**: Create a test DB, backup via API, verify integrity.
3. **Lock contention test**: Two threads attempt sync simultaneously, verify no interleaving.
4. **Scanner fallback test**: Archive exists → reads from archive. Archive missing → reads from source.
5. **Integration test**: Full sync → scan → parse cycle with test fixtures.

### Scope

**In scope (this spec):**
- `hub/data/archive_sync.py` — sync engine
- `SessionInfo` field additions (`source_path`, `archive_path`)
- Scanner path resolution (scanner-time assignment of `jsonl_path`)
- `AntiGravityParser` brain path fix (use archive path, not hardcoded source)
- Startup/refresh sync integration (background thread + progress)
- Mirror-only session detection
- Sync log

**Deferred:**
- Git mode (feature-flag for users who want versioning — add later if needed)
- Manifest with SHA-256 per file (optimize when scale demands it)
- Retention policies (age-based, size-based purge rules)
- Remote backup (push archive to a remote)
- Purge UI (context menu for removing archived sessions)
- Archive status in preferences

### Verification

```bash
# Mirror parity (line counts match source for live files)
diff <(wc -l ~/.claude/projects/*/*.jsonl 2>/dev/null | sort) \
     <(wc -l ~/.local/share/claude-dossier/archive/claude/projects/*/*.jsonl 2>/dev/null | sort)

# SQLite snapshot integrity
sqlite3 ~/.local/share/claude-dossier/snapshots/codex_state_5.sqlite "PRAGMA integrity_check;"

# Archive disk usage
du -sh ~/.local/share/claude-dossier/

# All mirrored JSONL files end with newline
find ~/.local/share/claude-dossier/archive -name '*.jsonl' -exec sh -c 'test "$(tail -c1 "$1")" = "" || echo "no trailing newline: $1"' _ {} \;

# Existing tests still pass
GSETTINGS_BACKEND=memory pytest tests/ -v

# Rotation scenario: truncate source, re-sync, verify both versions exist
```

### Rollback

- Toggle off archive (config flag or remove archive_root parameter) → scanners read source directly
- Rename `~/.local/share/claude-dossier/archive` → `archive.bak` to disable without data loss
- Revert `SessionInfo` to use `jsonl_path` only (one-line change in scanner)
