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
