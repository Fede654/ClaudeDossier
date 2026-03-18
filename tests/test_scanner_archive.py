import json
from pathlib import Path


def test_claude_scanner_prefers_archive(tmp_path):
    from hub.data.session_scanner import ClaudeScanner

    source = tmp_path / "source" / "-home-user-proj"
    source.mkdir(parents=True)
    (source / "sessions-index.json").write_text(json.dumps({
        "version": 1, "originalPath": "/home/user/proj", "entries": []
    }))
    (source / "abc.jsonl").write_text('{"type":"user","message":{"content":"hello"},"uuid":"u1","timestamp":"2026-01-01T00:00:00Z"}\n')

    archive = tmp_path / "archive" / "-home-user-proj"
    archive.mkdir(parents=True)
    (archive / "sessions-index.json").write_text(json.dumps({
        "version": 1, "originalPath": "/home/user/proj", "entries": []
    }))
    (archive / "abc.jsonl").write_text('{"type":"user","message":{"content":"hello"},"uuid":"u1","timestamp":"2026-01-01T00:00:00Z"}\n')

    scanner = ClaudeScanner(projects_root=source.parent, archive_projects_root=archive.parent)
    projects = scanner.scan()
    sessions = [s for p in projects for s in p.sessions]
    assert len(sessions) == 1
    assert sessions[0].jsonl_path == archive / "abc.jsonl"
    assert sessions[0].source_path == source / "abc.jsonl"
    assert sessions[0].archive_path == archive / "abc.jsonl"


def test_claude_scanner_falls_back_to_source(tmp_path):
    from hub.data.session_scanner import ClaudeScanner

    source = tmp_path / "source" / "-home-user-proj"
    source.mkdir(parents=True)
    (source / "sessions-index.json").write_text(json.dumps({
        "version": 1, "originalPath": "/home/user/proj", "entries": []
    }))
    (source / "abc.jsonl").write_text('{"type":"user","message":{"content":"hi"},"uuid":"u1","timestamp":"2026-01-01T00:00:00Z"}\n')

    scanner = ClaudeScanner(projects_root=source.parent, archive_projects_root=tmp_path / "no_archive")
    projects = scanner.scan()
    sessions = [s for p in projects for s in p.sessions]
    assert len(sessions) == 1
    assert sessions[0].jsonl_path == source / "abc.jsonl"
    assert sessions[0].source_path == source / "abc.jsonl"
    assert sessions[0].archive_path is None


def test_mirror_only_property(tmp_path):
    from hub.data.session_scanner import SessionInfo
    from datetime import datetime, timezone
    from pathlib import Path

    existing_file = tmp_path / "exists.jsonl"
    existing_file.write_text("{}\n")
    missing_file = tmp_path / "gone.jsonl"

    now = datetime.now(tz=timezone.utc)

    # Session with live source
    s1 = SessionInfo(
        session_id="s1", first_prompt="", message_count=1,
        created=now, modified=now, git_branch="", project_path="",
        is_sidechain=False, jsonl_path=existing_file,
        source_path=existing_file, archive_path=existing_file,
    )
    assert s1.is_mirror_only is False

    # Session where source is gone but archive exists
    s2 = SessionInfo(
        session_id="s2", first_prompt="", message_count=1,
        created=now, modified=now, git_branch="", project_path="",
        is_sidechain=False, jsonl_path=existing_file,
        source_path=missing_file, archive_path=existing_file,
    )
    assert s2.is_mirror_only is True

    # Session with no archive
    s3 = SessionInfo(
        session_id="s3", first_prompt="", message_count=1,
        created=now, modified=now, git_branch="", project_path="",
        is_sidechain=False, jsonl_path=existing_file,
        source_path=existing_file,
    )
    assert s3.is_mirror_only is False
