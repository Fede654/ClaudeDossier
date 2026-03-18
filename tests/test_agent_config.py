from pathlib import Path


def test_discovers_claude_config(tmp_path):
    from hub.data.agent_config import discover_agent_configs
    proj = tmp_path / "myproject"
    proj.mkdir()
    (proj / "CLAUDE.md").write_text("# Instructions")
    mem = tmp_path / "claude_memory"
    mem.mkdir()
    (mem / "MEMORY.md").write_text("# Index\n")
    (mem / "proj.md").write_text("---\nname: Test\ndescription: x\ntype: project\n---\nContent\n")

    configs = discover_agent_configs(
        str(proj), [],
        claude_global=tmp_path / "global_claude.md",
        claude_memory_dir=mem,
    )
    claude = next(c for c in configs if c.agent == "claude")
    assert claude.has_data is True
    assert claude.project_instructions == proj / "CLAUDE.md"
    assert claude.memory_dir == mem
    assert len(claude.memory_files) == 1


def test_discovers_codex_config(tmp_path):
    from hub.data.agent_config import discover_agent_configs
    proj = tmp_path / "myproject"
    proj.mkdir()
    (proj / "AGENTS.md").write_text("# Agents")

    configs = discover_agent_configs(str(proj), [], codex_config=tmp_path / "config.toml")
    codex = next(c for c in configs if c.agent == "codex")
    assert codex.has_data is True
    assert codex.project_instructions == proj / "AGENTS.md"


def test_discovers_antigravity_config(tmp_path):
    from hub.data.agent_config import discover_agent_configs
    gemini_md = tmp_path / "GEMINI.md"
    gemini_md.write_text("# Gemini agent")

    configs = discover_agent_configs(str(tmp_path / "proj"), [], ag_global=gemini_md)
    ag = next(c for c in configs if c.agent == "antigravity")
    assert ag.has_data is True
    assert ag.global_instructions == gemini_md


def test_no_data_returns_correct_flags(tmp_path):
    from hub.data.agent_config import discover_agent_configs
    configs = discover_agent_configs(str(tmp_path / "empty"), [], claude_global=tmp_path / "nope.md")
    claude = next(c for c in configs if c.agent == "claude")
    assert claude.has_data is True  # always shown
    codex = next(c for c in configs if c.agent == "codex")
    assert codex.has_data is False
