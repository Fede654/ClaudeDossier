import json
import hashlib
from pathlib import Path


def test_sync_copies_new_file(tmp_path):
    """New file in source gets copied to archive."""
    from hub.data.archive_sync import sync_text_files
    source = tmp_path / "source"
    archive = tmp_path / "archive"
    source.mkdir()
    archive.mkdir()
    (source / "test.jsonl").write_text('{"type":"user"}\n{"type":"assistant"}\n')

    actions = sync_text_files(source, archive, extensions={".jsonl"})
    assert (archive / "test.jsonl").exists()
    assert (archive / "test.jsonl").read_text() == '{"type":"user"}\n{"type":"assistant"}\n'
    assert any(a["action"] == "copy" for a in actions)


def test_sync_appends_grown_file(tmp_path):
    """Source file grew (same prefix) — append new content to mirror."""
    from hub.data.archive_sync import sync_text_files
    source = tmp_path / "source"
    archive = tmp_path / "archive"
    source.mkdir()
    archive.mkdir()
    original = '{"line":1}\n{"line":2}\n'
    (archive / "test.jsonl").write_text(original)
    (source / "test.jsonl").write_text(original + '{"line":3}\n')

    actions = sync_text_files(source, archive, extensions={".jsonl"})
    content = (archive / "test.jsonl").read_text()
    assert '{"line":3}' in content
    assert content.startswith('{"line":1}')
    assert any(a["action"] == "append" for a in actions)


def test_sync_detects_rotation(tmp_path):
    """Source file has different prefix — rotation detected, both preserved."""
    from hub.data.archive_sync import sync_text_files
    source = tmp_path / "source"
    archive = tmp_path / "archive"
    source.mkdir()
    archive.mkdir()
    (archive / "test.jsonl").write_text('{"old":"data"}\n')
    (source / "test.jsonl").write_text('{"new":"rotated"}\n')

    actions = sync_text_files(source, archive, extensions={".jsonl"})
    rotated = [f for f in archive.iterdir() if "pre-rotation" in f.name]
    assert len(rotated) == 1
    assert '{"old":"data"}' in rotated[0].read_text()
    assert '{"new":"rotated"}' in (archive / "test.jsonl").read_text()
    assert any(a["action"] == "rotation_detected" for a in actions)


def test_sync_preserves_deleted_source(tmp_path):
    """Source file gone — mirror keeps it, no action."""
    from hub.data.archive_sync import sync_text_files
    source = tmp_path / "source"
    archive = tmp_path / "archive"
    source.mkdir()
    archive.mkdir()
    (archive / "orphan.jsonl").write_text('{"preserved":"yes"}\n')

    actions = sync_text_files(source, archive, extensions={".jsonl"})
    assert (archive / "orphan.jsonl").exists()
    assert (archive / "orphan.jsonl").read_text() == '{"preserved":"yes"}\n'


def test_sync_tail_safe_truncation(tmp_path):
    """Partial last line gets truncated to last complete newline."""
    from hub.data.archive_sync import sync_text_files
    source = tmp_path / "source"
    archive = tmp_path / "archive"
    source.mkdir()
    archive.mkdir()
    (source / "test.jsonl").write_text('{"complete":true}\n{"partial":tr')

    actions = sync_text_files(source, archive, extensions={".jsonl"})
    content = (archive / "test.jsonl").read_text()
    assert content == '{"complete":true}\n'
    assert content.endswith("\n")


def test_sync_walks_subdirectories(tmp_path):
    """Sync walks nested directory structure."""
    from hub.data.archive_sync import sync_text_files
    source = tmp_path / "source"
    archive = tmp_path / "archive"
    (source / "sub" / "deep").mkdir(parents=True)
    archive.mkdir()
    (source / "sub" / "deep" / "session.jsonl").write_text('{"ok":true}\n')

    sync_text_files(source, archive, extensions={".jsonl"})
    assert (archive / "sub" / "deep" / "session.jsonl").exists()


def test_sync_respects_extensions_filter(tmp_path):
    """Only files with matching extensions are synced."""
    from hub.data.archive_sync import sync_text_files
    source = tmp_path / "source"
    archive = tmp_path / "archive"
    source.mkdir()
    archive.mkdir()
    (source / "good.jsonl").write_text('{"ok":true}\n')
    (source / "skip.pb").write_bytes(b"\x00" * 100)

    sync_text_files(source, archive, extensions={".jsonl"})
    assert (archive / "good.jsonl").exists()
    assert not (archive / "skip.pb").exists()
