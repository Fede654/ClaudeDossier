# ClaudeDossier Data Format Reference

> **Last verified: 2026-03-18** | Claude Code 2.1.78 | Codex CLI 0.107.0 | Anti-Gravity (Electron)
> **Line numbers verified against**: `b9eaba4` — re-check references if parser files have changed since this commit.

This document is the authoritative reference for the data formats ClaudeDossier reads from each AI agent platform. It covers storage layouts, event schemas, what the current parsers handle (and what they drop), and how to preserve data before it disappears.

---

## Status Overview

| Source | What Works | What's Broken | Untapped Resources |
|--------|-----------|---------------|-------------------|
| **Claude Code** | Orphan JSONL discovery, user/assistant text parsing | sessions-index.json (100% stale), tool_use/tool_result/thinking blocks dropped | — |
| **Codex CLI** | Scanner finds JSONL files, parser handles `response_item` payloads | Parser also checks for flat `text`/`role` schema that doesn't match real data | `state_5.sqlite` (307 threads, richer metadata than JSONL) |
| **Anti-Gravity** | state.vscdb trajectory summaries (titles + turn text) | .pb decryption (AES-GCM, Electron safeStorage key inaccessible) | `brain/` directory (plaintext markdown — task descriptions, plans, walkthroughs) |

---

## 1. Claude Code Sessions

### 1.1 Storage Layout

```
~/.claude/projects/<url-encoded-path>/
├── sessions-index.json      # Metadata index (mostly stale)
├── <session-uuid>.jsonl      # Conversation transcripts
├── <session-uuid>.jsonl      # ...more sessions
└── ...
```

- **projects root**: `~/.claude/projects/` — one subdirectory per project, named by URL-encoding the original filesystem path
- **sessions-index.json**: Contains `originalPath`, plus an `entries[]` array with session metadata (`sessionId`, `firstPrompt`, `messageCount`, `created`, `modified`, `gitBranch`, `projectPath`, `isSidechain`)
- **JSONL files**: One per session, named `<session-uuid>.jsonl`

**BUG — 100% index-to-file miss rate**: Claude Code rotates and deletes JSONL files aggressively. On this system, 0 of 139 indexed sessions had their JSONL files present. The index is effectively a lie.

**Workaround**: ClaudeDossier discovers "orphan" JSONL files via glob (`*.jsonl`) that exist in the project directory but aren't in the index. This is currently the *only* working path for finding sessions.

> **Ref**: `hub/data/session_scanner.py:111–155` (ClaudeScanner) — index parsing at line 122, orphan discovery at line 147

### 1.2 JSONL Event Schema

Each line is a JSON object. Top-level fields:

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Event type: `"user"`, `"assistant"`, `"progress"`, `"file-history-snapshot"`, `"queue-operation"` |
| `uuid` | string | Event UUID |
| `timestamp` | string (ISO 8601) | When the event occurred |
| `message` | object | Contains `content` (the actual message payload) |
| `isSidechain` | boolean | Whether this is a background/sidechain message |
| `gitBranch` | string | Current git branch at time of event |
| `cwd` | string | Working directory |
| `version` | string | Claude Code version |
| `sessionId` | string | Session UUID |

**`message.content`** is either:
- A plain string (older format)
- An array of content blocks (current format, following the Anthropic Messages API)

**Content block types** (from the [Anthropic Messages API](https://docs.anthropic.com/en/api/messages)):

| Block type | Description | Parsed by Dossier? |
|-----------|-------------|:-------------------:|
| `text` | Plain text response | Yes |
| `tool_use` | Tool invocation (name, input JSON) | **No** — dropped |
| `tool_result` | Tool execution result | **No** — dropped |
| `thinking` | Extended thinking trace | **No** — dropped |
| `image` | Image content | **No** — dropped |
| `document` | Document attachment | **No** — dropped |

### 1.3 System Prompt Hierarchy (NOT in JSONL)

The system prompt is **never stored** in JSONL files. It's assembled at runtime in three layers:

1. **Base prompt** — Compiled into the Claude Code binary. Defines tools, tone, behavior rules. Not persisted anywhere accessible.
2. **system-reminder injections** — Injected per-turn via `<system-reminder>` tags. Includes:
   - CLAUDE.md chain: `~/.claude/CLAUDE.md` → `$PROJECT/CLAUDE.md` → `$PROJECT/.claude/CLAUDE.md`
   - Skill definitions and metadata
   - `gitStatus` snapshot (branch, recent commits, dirty files)
   - `currentDate`
   - Available tools list
3. **Per-message metadata** — Fields like `cwd`, `gitBranch`, `version` in the JSONL record. This is the *only* system-prompt-adjacent data that's persisted.

> **Ref**: [Claude Code docs](https://code.claude.com/docs/en/overview), [Session continuation deep-dive](https://blog.fsck.com/releases/2026/02/22/claude-code-session-continuation/)

### 1.4 Parser Gap Analysis

**ClaudeParser** (`hub/data/session_parser.py:55–97`):

| What it reads | How |
|--------------|-----|
| `user` and `assistant` messages | Maps `type` field via `_TYPE_MAP` (line 21–26) |
| Text from content blocks | `_text()` helper (line 38–43) joins `text` fields from block arrays |
| Timestamps | ISO 8601 parsing (line 46–52) |
| Sidechain flag | `isSidechain` field (line 95) |

| What it drops | Why |
|--------------|-----|
| `tool_use` blocks | `_text()` only extracts `.get("text", "")` — tool_use blocks have `name`/`input` instead |
| `tool_result` blocks | Same reason — content is in a different structure |
| `thinking` blocks | Has `thinking` field, not `text` |
| `queue-operation` events | Explicitly skipped (line 77–78) |
| `progress` events | Filtered unless `include_progress=True` (line 82–83) |

### 1.5 Preservation

- **Back up `~/.claude/projects/`** regularly — JSONL files are deleted without warning during rotation
- `sessions-index.json` is metadata-only; actual conversation content is exclusively in JSONL files
- The index may reference sessions whose JSONL files no longer exist

> **Ref**: [Auto-save strategies](https://jeradbitner.com/blog/claude-code-auto-save-conversations), [Hidden conversation history](https://kentgigger.com/posts/claude-code-conversation-history)

---

## 2. OpenAI Codex CLI

### 2.1 Storage Layout

```
~/.codex/
├── sessions/
│   └── YYYY/MM/DD/
│       └── rollout-*.jsonl       # Session transcripts
├── state_5.sqlite                # Primary state database
├── config.toml                   # User configuration
└── history.jsonl                 # Command history
```

- **JSONL sessions**: Organized by date under `~/.codex/sessions/`
- **SQLite database**: `state_5.sqlite` — the primary data store, much richer than JSONL
- **Config**: TOML format at `~/.codex/config.toml`

> **Ref**: [Codex CLI GitHub](https://github.com/openai/codex), [Codex CLI Reference](https://developers.openai.com/codex/cli/reference)

### 2.2 JSONL Event Schema (Verified)

Each line is a JSON object. Two event types:

**Line 1 — Session metadata:**
```json
{
  "type": "session_meta",
  "session_id": "...",
  "model": "...",
  "sandbox_policy": "...",
  "config": { ... }
}
```

**Lines 2+ — Response items:**
```json
{
  "type": "response_item",
  "payload": {
    "type": "message",
    "role": "developer" | "user" | "assistant",
    "content": [
      { "type": "input_text", "text": "..." },
      { "type": "output_text", "text": "..." },
      { "type": "text", "text": "..." }
    ]
  }
}
```

**Notable details:**
- Codex uses `"developer"` role (not `"system"`) for system-level messages
- Working directory is embedded as `<cwd>...</cwd>` XML tags within content text
- Content block types: `input_text` (user input), `output_text` (assistant output), `text` (generic)

### 2.3 SQLite Schema (`state_5.sqlite`)

Key table — **threads**:

| Column | Type | Description |
|--------|------|-------------|
| `id` | text | Thread UUID |
| `title` | text | Conversation title |
| `created_at` | text | Creation timestamp |
| `cwd` | text | Working directory |
| `model_provider` | text | e.g. "openai" |
| `sandbox_policy` | text | Sandbox configuration |
| `git_sha` | text | Git commit at session start |
| `git_branch` | text | Git branch at session start |

Additional tables: `logs`, `jobs`, `agent_jobs` — structure not fully mapped.

**307 threads** available on this system — completely untapped by Dossier.

### 2.4 Parser Gap Analysis

**CodexScanner** (`hub/data/session_scanner.py:157–243`):
- Root path: `~/.codex/sessions/` (correct)
- Discovery: `rglob("*.jsonl")` finds all JSONL files (works)
- CWD extraction: Parses `<cwd>...</cwd>` tags from content (line 208–210)
- Groups sessions by CWD into ProjectInfo objects

**CodexParser** (`hub/data/session_parser.py:99–153`):
- Handles both the legacy flat schema (`text`/`role` fields, lines 122–129) and the real `response_item` payload schema (lines 131–151)
- Content block types `text`, `input_text`, `output_text` all extracted (line 144)
- Maps `"developer"` role to `PROGRESS` type (line 139) — debatable, could be USER

| What it reads | Status |
|--------------|--------|
| `session_meta` events | Skipped (no `text` or `payload.type=="message"`) |
| `response_item` with `payload.role` in user/assistant | Parsed correctly |
| `developer` role messages | Mapped to PROGRESS (filtered by default) |

| What's missing |
|----------------|
| SQLite `state_5.sqlite` — not read at all (richer metadata: titles, git info, 307 threads) |

### 2.5 Preservation

- `state_5.sqlite` is the primary store — richer than JSONL
- JSONL files under `sessions/` are secondary transcripts
- Back up both together: `~/.codex/state_5.sqlite` + `~/.codex/sessions/`

> **Ref**: [Codex Advanced Config](https://developers.openai.com/codex/config-advanced)

---

## 3. Anti-Gravity (Google Gemini IDE)

> **Note**: Anti-Gravity is the Electron-based Google Gemini IDE. It is **not** the same as [Gemini CLI](https://github.com/google-gemini/gemini-cli), which uses plaintext JSON.

### 3.1 Storage Layout

```
~/.gemini/antigravity/
├── conversations/
│   └── *.pb                      # Encrypted Protobuf (AES-GCM)
└── brain/
    └── {conversation-id}/
        ├── task.md               # Task description (PLAINTEXT)
        ├── implementation_plan.md # Implementation plan (PLAINTEXT)
        ├── walkthrough.md        # Code walkthrough (PLAINTEXT)
        ├── *.metadata.json       # Structured artifact metadata
        └── *.resolved            # Version history

~/.config/Antigravity/User/globalStorage/
└── state.vscdb                   # SQLite state database
```

### 3.2 Encryption Details (`.pb` files)

- **Encryption**: AES-GCM (128 or 256-bit), key derived via PBKDF2-SHA1
- **Key management**: Electron `safeStorage` API → OS keyring
- **Linux keyring backends**: `gnome_libsecret`, `kwallet`, `basic_text` (Chromium selection logic)
- **On this system**: `secret-tool lookup` does NOT return the key — needs further investigation
- **Research scripts** (in repo root): `decrypt_go.go`, `decrypt_bruteforce.go`, `decrypt_pb.mjs`, `deep_dive.py`, `deep_dive2.py`

> **Ref**: [Electron safeStorage API](https://www.electronjs.org/docs/latest/api/safe-storage)

### 3.3 state.vscdb Protobuf Structure (Reverse-Engineered)

The state database is a SQLite file (VS Code storage format). The key `antigravityUnifiedStateSync.trajectorySummaries` contains a base64-encoded Protobuf blob.

**Decoded structure** (no `.proto` file exists — decoded from wire format):

```
outer (base64 → Protobuf)
└── field 1 (repeated) — one per conversation
    ├── field 1.1 = conversation UUID (string)
    └── field 1.2 = turn blob (bytes)
        └── field 1 = base64-encoded inner Protobuf
            ├── field 1  = title (string)
            ├── field 4  = session/notification UUID (string)
            ├── field 12 = first turn (Protobuf)
            └── field 14 = later turns (Protobuf, may repeat)
                └── field 1
                    └── field 94
                        ├── field 1 = task/step title (string)
                        └── field 2 = AI response text (string)
```

> **Ref**: `hub/data/antigravity_vscdb.py:1–224` — full Protobuf wire-format decoder with no external dependencies

### 3.4 Brain Directory (UNTAPPED)

The `brain/` directory contains **plaintext markdown** files organized by conversation ID:

| File | Content |
|------|---------|
| `task.md` | Task description / user request |
| `implementation_plan.md` | AI-generated implementation plan |
| `walkthrough.md` | Code walkthrough / explanation |
| `*.metadata.json` | Structured artifact metadata |
| `*.resolved` | Version history of artifacts |

**9 conversations with brain data** available on this system. This is the highest-value untapped data source — rich, structured, plaintext, and trivial to parse.

### 3.5 Parser Gap Analysis

**AntiGravityScanner** (`hub/data/session_scanner.py:246–277`):
- Lists `.pb` files only (line 256)
- Does NOT scan `brain/` directory
- Creates placeholder SessionInfo with `message_count=1`

**AntiGravityParser** (`hub/data/session_parser.py:156–231`):
- Reads state.vscdb trajectory summaries via `antigravity_vscdb.load_trajectories()`
- Extracts titles and turn text from the Protobuf structure
- Falls back to "Opaque session" message when no cached summary exists

| What it reads | What's missing |
|--------------|----------------|
| state.vscdb summaries (titles + turn text) | `brain/` directory (plaintext markdown — highest value) |
| Conversation UUIDs from .pb filenames | .pb file contents (blocked by encryption) |

### 3.6 Preservation

- **`brain/` directory** — Back up immediately. Unencrypted, high-value, and its persistence behavior is unknown.
- **`state.vscdb`** — Ephemeral UI cache. May be cleared on app updates or resets.
- **`.pb` files** — Require the Electron safeStorage key. If Anti-Gravity is uninstalled, the key may be lost permanently, making these files irrecoverable.

---

## 4. Anthropic Messages API Reference

ClaudeDossier's JSONL records use the [Anthropic Messages API](https://docs.anthropic.com/en/api/messages) content block format. Key types:

### Content Block Types

| Type | Fields | Description |
|------|--------|-------------|
| `text` | `text` | Plain text content |
| `tool_use` | `id`, `name`, `input` | Tool invocation — `name` is the tool, `input` is the JSON arguments |
| `tool_result` | `tool_use_id`, `content` | Result from a tool execution |
| `thinking` | `thinking` | Extended thinking / chain-of-thought trace |
| `image` | `source` (type, media_type, data) | Base64-encoded image |
| `document` | `source` (type, media_type, data) | Document attachment (PDF, etc.) |

### Message Structure

```json
{
  "role": "user" | "assistant",
  "content": [
    { "type": "text", "text": "..." },
    { "type": "tool_use", "id": "toolu_...", "name": "Read", "input": { "file_path": "..." } }
  ]
}
```

> **Ref**: [Anthropic Messages API](https://docs.anthropic.com/en/api/messages), [Tool Use](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)

---

## Appendix A: Consolidated References

### Official Documentation

| Source | URL |
|--------|-----|
| Claude Code docs | https://code.claude.com/docs/en/overview |
| Anthropic Messages API | https://docs.anthropic.com/en/api/messages |
| Anthropic Tool Use | https://docs.anthropic.com/en/docs/build-with-claude/tool-use |
| Claude Code GitHub | https://github.com/anthropics/claude-code |
| Codex CLI GitHub | https://github.com/openai/codex |
| Codex CLI Reference | https://developers.openai.com/codex/cli/reference |
| Codex Advanced Config | https://developers.openai.com/codex/config-advanced |
| Electron safeStorage | https://www.electronjs.org/docs/latest/api/safe-storage |
| Gemini CLI (NOT Anti-Gravity) | https://github.com/google-gemini/gemini-cli |

### Community / Blog References

| Source | URL |
|--------|-----|
| Session continuation deep-dive | https://blog.fsck.com/releases/2026/02/22/claude-code-session-continuation/ |
| Hidden conversation history | https://kentgigger.com/posts/claude-code-conversation-history |
| Auto-save strategies | https://jeradbitner.com/blog/claude-code-auto-save-conversations |
| DuckDB JSONL analysis | https://liambx.com/blog/claude-code-log-analysis-with-duckdb/ |
| JSONL→Markdown browser | https://github.com/withLinda/claude-JSONL-browser |
| JSONL→HTML converter | https://github.com/daaain/claude-code-log |
| Conversation extractor | https://github.com/ZeroSumQuant/claude-conversation-extractor |
| Claude Code transcripts | https://github.com/simonw/claude-code-transcripts |

## Appendix B: Exploratory Scripts

Scripts in the repository root from reverse-engineering efforts:

| Script | Purpose | Outcome |
|--------|---------|---------|
| `decrypt_go.go` | Go-based .pb decryption attempt | Failed — could not extract safeStorage key |
| `decrypt_bruteforce.go` | Brute-force key search for .pb files | Failed — key space too large |
| `decrypt_pb.mjs` | Node.js Electron safeStorage decryption | Failed — requires running Electron context |
| `deep_dive.py` | Python protobuf analysis of .pb files | Partial — mapped wire format, blocked by encryption |
| `deep_dive2.py` | Extended protobuf/encryption analysis | Partial — confirmed AES-GCM, key derivation path |
| `pb_walker.py` | Generic protobuf wire-format walker | Succeeded — used to map state.vscdb structure |
| `check_ldb.py` | LevelDB inspection for cached keys | Failed — no relevant keys found |
| `hub/data/antigravity_vscdb.py` | state.vscdb trajectory parser | **Succeeded** — integrated into Dossier |
