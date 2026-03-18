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
