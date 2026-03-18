"""Codex configuration tab — config file + AGENTS.md editor."""
from __future__ import annotations

import tomllib
from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk

from hub.data.agent_config import AgentConfig


class CodexTab(Adw.PreferencesPage):
    __gtype_name__ = 'CodexTab'

    def __init__(self):
        super().__init__(title="Codex", icon_name="document-edit-symbolic")
        self._project_path: str | None = None
        self._agents_text_view: Gtk.TextView | None = None

        # Config group — populated lazily in load()
        self._config_group = Adw.PreferencesGroup(title="Configuration")
        self.add(self._config_group)

        # AGENTS.md group — populated lazily in load()
        self._agents_group = Adw.PreferencesGroup(title="AGENTS.md")
        self.add(self._agents_group)

    # ---------------------------------------------------------------------- API

    def load(self, project_path: str, config: AgentConfig) -> None:
        """Populate the tab for the given project and agent config."""
        self._project_path = project_path
        self._agents_text_view = None
        self._rebuild_config(config)
        self._rebuild_agents(project_path)

    # -------------------------------------------------------- config rendering

    def _rebuild_config(self, config: AgentConfig) -> None:
        """Clear and repopulate the config group."""
        # Remove existing children
        child = self._config_group.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            try:
                self._config_group.remove(child)
            except Exception:
                pass
            child = nxt

        if config.config_file is None:
            row = Adw.ActionRow(
                title="No config file found",
                subtitle="~/.codex/config.toml not present",
            )
            row.add_css_class("dim-label")
            self._config_group.add(row)
            return

        self._config_group.set_description(str(config.config_file))

        try:
            data = tomllib.loads(config.config_file.read_text())
        except Exception as e:
            row = Adw.ActionRow(title="Error reading config", subtitle=str(e))
            self._config_group.add(row)
            return

        model = data.get("model")
        if model:
            row = Adw.ActionRow(title="Model", subtitle=str(model))
            self._config_group.add(row)

        approval = data.get("approval_policy") or data.get("approvalPolicy")
        if approval:
            row = Adw.ActionRow(title="Approval Policy", subtitle=str(approval))
            self._config_group.add(row)

        if not model and not approval:
            row = Adw.ActionRow(
                title="Config loaded",
                subtitle="No model or approval_policy keys found",
            )
            self._config_group.add(row)

    # ------------------------------------------------------- AGENTS.md rendering

    def _rebuild_agents(self, project_path: str) -> None:
        """Clear and repopulate the AGENTS.md group."""
        # Remove existing children
        child = self._agents_group.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            try:
                self._agents_group.remove(child)
            except Exception:
                pass
            child = nxt

        agents_path = Path(project_path) / "AGENTS.md"

        if not agents_path.exists():
            status = Adw.StatusPage()
            status.set_title("No AGENTS.md")
            status.set_description("Create an AGENTS.md in the project root to instruct Codex.")
            status.set_icon_name("document-new-symbolic")
            # Wrap in a box to add into group
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            box.append(status)
            self._agents_group.add(box)
            return

        try:
            content = agents_path.read_text()
        except OSError:
            content = "(unreadable)"

        block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        block.add_css_class("card")

        # Header row
        hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hdr_box.set_margin_start(10)
        hdr_box.set_margin_top(8)
        hdr_box.set_margin_end(10)
        hdr_box.set_margin_bottom(6)

        try:
            home = Path.home()
            rel = "~/" + str(agents_path.relative_to(home))
        except ValueError:
            rel = str(agents_path)

        hdr = Gtk.Label(label=f"Project  \u00b7  {rel}", xalign=0, hexpand=True)
        hdr.add_css_class("caption")
        hdr.add_css_class("heading")
        hdr_box.append(hdr)

        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.set_valign(Gtk.Align.CENTER)
        save_btn.connect("clicked", self._save_agents)
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
        self._agents_text_view = tv

        sw = Gtk.ScrolledWindow()
        sw.set_min_content_height(200)
        sw.set_max_content_height(600)
        sw.set_propagate_natural_height(True)
        sw.set_child(tv)
        block.append(sw)

        self._agents_group.add(block)

    # -------------------------------------------------------------------- save

    def _save_agents(self, _btn) -> None:
        if not self._project_path or not self._agents_text_view:
            return
        buf = self._agents_text_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        target = Path(self._project_path) / "AGENTS.md"
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
