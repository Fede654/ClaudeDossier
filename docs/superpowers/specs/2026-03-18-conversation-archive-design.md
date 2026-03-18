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

#### 2. Text File Sync (JSONL, Markdown, JSON)

For each source directory, walk all files. For each file:

**New file** (exists in source, not in mirror): Copy to mirror using atomic temp+rename.

**Existing file — source grew** (append detection): Compare first 4KB hash of source vs mirror. If identical prefix → source was appended to → tail-safe copy: read source from mirror's byte offset to EOF, append to mirror, truncate at last complete newline.

**Existing file — source diverged** (rotation detection): First 4KB hash differs → source was rotated/replaced. Keep the existing mirror file (rename to `<name>.pre-rotation-<timestamp>`), copy the new source content as the primary file. Both versions preserved.

**Source file gone** (deleted/rotated away): Mirror keeps it. No action. These are "mirror-only" sessions.

**Tail-safe copy**: Always copy up to the last complete newline (`\n`). If the last byte isn't `\n`, truncate to the previous one. This prevents capturing partial JSON lines from in-progress writes.

**Atomic writes**: All copies go to a temp file in the same directory, then `os.rename()` (atomic on Linux).

#### 3. SQLite Snapshots

For each SQLite source (`~/.codex/state_5.sqlite`, `~/.config/Antigravity/User/globalStorage/state.vscdb`):

1. Check source `mtime` against last snapshot `mtime` (stored in sync.log). If unchanged, skip.
2. Use `sqlite3.backup()` API (handles WAL/journal correctly, safe against concurrent writers).
3. Write to temp file, verify with `PRAGMA integrity_check`, then atomic rename to final path.

This avoids the 12.7GB raw copy problem — `sqlite3.backup()` is incremental when possible, and mtime gating means it only runs when the source actually changed.

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
    source_path: Path | None = None    # Original location (provenance)
    archive_path: Path | None = None   # Mirror location (read from this)
```

- `source_path`: Where the file actually lives on the source platform. Shown in UI for provenance.
- `archive_path`: Where the mirrored copy lives. Parsers and search index read from this.
- `jsonl_path`: Becomes an alias for `archive_path` (backward compatibility). Falls back to `source_path` if archive doesn't exist.

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

None. Parsers receive a `Path` and read it. They don't care whether it points to source or mirror. The only change is which path they receive.

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

#### Archive Status

Add to preferences or status bar:
- Archive size (du of archive/ + snapshots/)
- Last sync time
- Session counts: source-live vs mirror-only

#### Purge

Context menu on a session: "Remove from archive". Deletes the mirror file and the sync.log entry. This is the only way to remove data from the archive — it never happens automatically.

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
- `SessionInfo` field additions
- Scanner path resolution
- Startup/refresh sync integration
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
