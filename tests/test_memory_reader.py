from pathlib import Path


def _make_memory(tmp_path, filename, name, desc, mtype, content):
    path = tmp_path / filename
    path.write_text(f"---\nname: {name}\ndescription: {desc}\ntype: {mtype}\n---\n\n{content}\n")
    return path


def _make_index(tmp_path, entries):
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
    assert reloaded[0].name == "Test"


def test_write_memory_mtime_check(tmp_path):
    import time
    from hub.data.memory_reader import read_memory_dir, write_memory, MtimeConflictError
    _make_memory(tmp_path, "test.md", "Test", "A test", "project", "V1.")
    entries = read_memory_dir(tmp_path)
    entry = entries[0]
    old_mtime = entry.mtime
    time.sleep(0.05)
    (tmp_path / "test.md").write_text("---\nname: Test\ndescription: A test\ntype: project\n---\n\nExternal edit.\n")
    entry.content = "My edit."
    try:
        write_memory(entry, expected_mtime=old_mtime)
        assert False, "Should have raised MtimeConflictError"
    except MtimeConflictError:
        pass


def test_create_memory(tmp_path):
    from hub.data.memory_reader import create_memory, read_memory_dir
    _make_index(tmp_path, [])
    entry = create_memory(tmp_path, name="New mem", type="feedback", description="A feedback", content="Don't do X.")
    assert entry.path.exists()
    assert "New mem" in entry.path.read_text()
    index = (tmp_path / "MEMORY.md").read_text()
    assert entry.path.name in index


def test_delete_memory(tmp_path):
    from hub.data.memory_reader import read_memory_dir, delete_memory
    _make_memory(tmp_path, "doomed.md", "Doomed", "Will be deleted", "project", "Bye.")
    _make_index(tmp_path, [("doomed.md", "Doomed")])
    entries = read_memory_dir(tmp_path)
    delete_memory(entries[0])
    assert not (tmp_path / "doomed.md").exists()
    index = (tmp_path / "MEMORY.md").read_text()
    assert "doomed.md" not in index
