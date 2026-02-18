from pathlib import Path
from datetime import datetime, timezone
from hub.data.session_scanner import ProjectInfo, SessionInfo


def _dt(day: int) -> datetime:
    return datetime(2026, 1, day, tzinfo=timezone.utc)


def _sess(sid: str, day: int) -> SessionInfo:
    return SessionInfo(sid, "p", 1, _dt(1), _dt(day), "main", "/p", False, Path("/f"))


def _proj(path: str, sessions=None) -> ProjectInfo:
    p = ProjectInfo(original_path=path, project_dir=Path("/fake"))
    p.sessions = sessions or []
    return p


def test_builds_hierarchy_from_original_path():
    from hub.data.tree_builder import TreeBuilder
    projects = [
        _proj("/home/user/repos/proj-a", [_sess("s1", 5)]),
        _proj("/home/user/repos/proj-b", [_sess("s2", 3)]),
    ]
    root = TreeBuilder(base="/home/user").build(projects)
    assert len(root.children) == 1
    assert root.children[0].name == "repos"
    assert len(root.children[0].children) == 2


def test_sorts_by_last_active_descending():
    from hub.data.tree_builder import TreeBuilder
    projects = [
        _proj("/home/user/old", [_sess("s1", 1)]),
        _proj("/home/user/new", [_sess("s2", 10)]),
    ]
    root = TreeBuilder(base="/home/user").build(projects)
    assert root.children[0].name == "new"
    assert root.children[1].name == "old"


def test_compact_collapses_single_child_intermediates():
    from hub.data.tree_builder import TreeBuilder
    projects = [_proj("/home/user/a/b/c/proj", [_sess("s1", 1)])]
    root = TreeBuilder(base="/home/user", compact=True).build(projects)
    # a → b → c should compact to a single node
    assert len(root.children) == 1
    assert "/" in root.children[0].name  # "a/b/c"


def test_compact_false_shows_full_depth():
    from hub.data.tree_builder import TreeBuilder
    projects = [_proj("/home/user/a/b/proj", [_sess("s1", 1)])]
    root = TreeBuilder(base="/home/user", compact=False).build(projects)
    assert root.children[0].name == "a"
    assert root.children[0].children[0].name == "b"


def test_session_count_propagates_up():
    from hub.data.tree_builder import TreeBuilder
    projects = [
        _proj("/u/repos/proj-a", [_sess("s1", 1), _sess("s2", 2)]),
        _proj("/u/repos/proj-b", [_sess("s3", 3)]),
    ]
    root = TreeBuilder(base="/u").build(projects)
    repos = root.children[0]
    assert repos.session_count == 3
