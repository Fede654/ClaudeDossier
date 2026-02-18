import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone


def make_index(tmp_path, original_path, entries):
    slug = original_path.replace('/', '-')
    proj_dir = tmp_path / slug
    proj_dir.mkdir(parents=True)
    index = {"version": 1, "originalPath": original_path, "entries": entries}
    (proj_dir / "sessions-index.json").write_text(json.dumps(index))
    return proj_dir


def _entry(sid, modified_day):
    return {
        "sessionId": sid,
        "firstPrompt": f"prompt for {sid}",
        "messageCount": 5,
        "created": f"2026-01-01T10:00:00.000Z",
        "modified": f"2026-01-{modified_day:02d}T10:00:00.000Z",
        "gitBranch": "main",
        "projectPath": "/home/user/proj",
        "isSidechain": False,
    }


def test_scanner_finds_projects(tmp_path):
    from hub.data.session_scanner import SessionScanner
    make_index(tmp_path, "/home/user/project-a", [])
    make_index(tmp_path, "/home/user/project-b", [])
    projects = SessionScanner(projects_root=tmp_path).scan()
    paths = {p.original_path for p in projects}
    assert paths == {"/home/user/project-a", "/home/user/project-b"}


def test_scanner_reads_session_entries(tmp_path):
    from hub.data.session_scanner import SessionScanner
    entries = [_entry("abc-123", 5)]
    make_index(tmp_path, "/home/user/proj", entries)
    projects = SessionScanner(projects_root=tmp_path).scan()
    assert len(projects[0].sessions) == 1
    s = projects[0].sessions[0]
    assert s.session_id == "abc-123"
    assert s.first_prompt == "prompt for abc-123"
    assert s.git_branch == "main"
    assert s.is_sidechain is False


def test_scanner_skips_dir_without_index(tmp_path):
    from hub.data.session_scanner import SessionScanner
    (tmp_path / "-home-user-orphan").mkdir()
    projects = SessionScanner(projects_root=tmp_path).scan()
    assert projects == []


def test_scanner_handles_malformed_index(tmp_path):
    from hub.data.session_scanner import SessionScanner
    d = tmp_path / "-home-user-broken"
    d.mkdir()
    (d / "sessions-index.json").write_text("NOT JSON{{{")
    projects = SessionScanner(projects_root=tmp_path).scan()
    assert projects == []


def test_project_last_active_is_max_modified(tmp_path):
    from hub.data.session_scanner import SessionScanner
    make_index(tmp_path, "/p", [_entry("s1", 1), _entry("s2", 15)])
    projects = SessionScanner(projects_root=tmp_path).scan()
    assert projects[0].last_active.day == 15
