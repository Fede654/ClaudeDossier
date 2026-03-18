"""Claude Code configuration tab — instructions chain + memory editor."""
from __future__ import annotations

from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk

from hub.data.agent_config import AgentConfig


def _claude_chain(project_path: str) -> list[tuple[str, bool]]:
    """Walk up from project_path to $HOME, then ~/.claude/CLAUDE.md.

    Returns a list of (path_str, exists) pairs ordered from project
    down to root, with the global config appended last.
    """
    chain = []
    p = Path(project_path)
    home = Path.home()
    while True:
        candidate = p / "CLAUDE.md"
        chain.append((str(candidate), candidate.exists()))
        if p == home or p.parent == p:
            break
        p = p.parent
    global_cfg = home / ".claude" / "CLAUDE.md"
    chain.append((str(global_cfg), global_cfg.exists()))
    return chain


class ClaudeTab(Adw.PreferencesPage):
    __gtype_name__ = 'ClaudeTab'

    def __init__(self):
        super().__init__(title="Claude", icon_name="document-edit-symbolic")
        self._text_view = None       # editable TextView for the project CLAUDE.md
        self._project_path: str | None = None
        self._memory_editor = None   # MemoryEditor widget, added lazily

        # Instructions chain group — always visible
        self._chain_group = Adw.PreferencesGroup(title="Instructions Chain")
        self._chain_group.set_description(
            "Load order: global \u2192 project (only present files shown)"
        )
        self._chain_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._chain_box.set_margin_top(4)
        self._chain_box.set_margin_bottom(8)
        self._chain_box.set_margin_start(6)
        self._chain_box.set_margin_end(6)
        self._chain_group.add(self._chain_box)
        self.add(self._chain_group)

    # ---------------------------------------------------------------------- API

    def load(self, project_path: str, config: AgentConfig) -> None:
        """Populate the tab for the given project and agent config."""
        self._project_path = project_path
        self._text_view = None
        self._rebuild_chain(project_path)
        self._rebuild_memory(config)

    # ---------------------------------------------------------- chain rendering

    def _rebuild_chain(self, project_path: str) -> None:
        """Clear and repopulate the CLAUDE.md chain box."""
        # Remove existing children
        child = self._chain_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._chain_box.remove(child)
            child = nxt

        chain = _claude_chain(project_path)
        # Reverse so we show global first, then down to project
        existing = [(p, e) for p, e in reversed(chain) if e]
        home = Path.home()
        proj = Path(project_path)

        if not existing:
            lbl = Gtk.Label(label="No CLAUDE.md files found in chain", xalign=0)
            lbl.add_css_class("dim-label")
            lbl.set_margin_start(8)
            lbl.set_margin_top(8)
            self._chain_box.append(lbl)
            return

        for idx, (path_str, _) in enumerate(existing):
            p = Path(path_str)
            is_project = (p.parent == proj)
            is_last = (idx == len(existing) - 1)

            if p == home / ".claude" / "CLAUDE.md":
                role = "Global  \u00b7  ~/.claude/CLAUDE.md"
            elif is_project:
                try:
                    rel = "~/" + str(p.relative_to(home))
                except ValueError:
                    rel = path_str
                role = f"Project  \u00b7  {rel}"
            else:
                try:
                    rel = "~/" + str(p.relative_to(home))
                except ValueError:
                    rel = path_str
                role = rel

            try:
                content = p.read_text()
            except OSError:
                content = "(unreadable)"

            block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            block.add_css_class("card")
            block.set_margin_bottom(2)

            # Header row: role label + optional Save button
            hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            hdr_box.set_margin_start(10)
            hdr_box.set_margin_top(8)
            hdr_box.set_margin_end(10)
            hdr_box.set_margin_bottom(6)

            hdr = Gtk.Label(label=role, xalign=0, hexpand=True)
            hdr.add_css_class("caption")
            hdr.add_css_class("heading")
            hdr_box.append(hdr)

            if is_last:
                save_btn = Gtk.Button(label="Save")
                save_btn.add_css_class("suggested-action")
                save_btn.set_valign(Gtk.Align.CENTER)
                save_btn.connect("clicked", self._save)
                hdr_box.append(save_btn)

            block.append(hdr_box)
            block.append(Gtk.Separator())

            tv = Gtk.TextView()
            tv.set_monospace(True)
            tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            tv.set_top_margin(8)
            tv.set_bottom_margin(8)
            tv.set_left_margin(10)
            tv.set_right_margin(10)
            tv.get_buffer().set_text(content)

            if is_last:
                # Keep reference for _save()
                self._text_view = tv
            else:
                tv.set_editable(False)
                tv.set_cursor_visible(False)

            sw = Gtk.ScrolledWindow()
            sw.set_min_content_height(200)
            sw.set_max_content_height(600)
            sw.set_propagate_natural_height(True)
            sw.set_child(tv)
            block.append(sw)

            self._chain_box.append(block)

    # --------------------------------------------------------- memory rendering

    def _rebuild_memory(self, config: AgentConfig) -> None:
        """Add or replace the MemoryEditor for this config."""
        if self._memory_editor is not None:
            try:
                self.remove(self._memory_editor)
            except Exception:
                pass
            self._memory_editor = None

        if config.memory_dir is not None:
            from hub.ui.memory_editor import MemoryEditor
            self._memory_editor = MemoryEditor(config.memory_dir)
            self.add(self._memory_editor)

    # -------------------------------------------------------------------- save

    def _save(self, _btn) -> None:
        if not self._project_path or not self._text_view:
            return
        buf = self._text_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        target = Path(self._project_path) / "CLAUDE.md"
        try:
            target.write_text(text)
            self._toast(f"Saved {target.name}")
        except Exception as e:
            self._toast(f"Error: {e}")

    def _toast(self, msg: str) -> None:
        win = self.get_root()
        if hasattr(win, "add_toast"):
            toast = Adw.Toast.new(msg)
            toast.set_timeout(0)
            win.add_toast(toast)
            GLib.timeout_add(1500, toast.dismiss)
