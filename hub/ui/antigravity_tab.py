"""Anti-Gravity configuration tab — GEMINI.md editor + brain artifacts."""
from __future__ import annotations

import shutil
from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk

from hub.data.agent_config import AgentConfig


class AntiGravityTab(Adw.PreferencesPage):
    __gtype_name__ = 'AntiGravityTab'

    def __init__(self):
        super().__init__(title="Anti-Gravity", icon_name="document-edit-symbolic")
        self._gemini_text_view: Gtk.TextView | None = None
        self._gemini_path: Path | None = None

        # GEMINI.md group
        self._gemini_group = Adw.PreferencesGroup(title="GEMINI.md")
        self.add(self._gemini_group)

        # Brain artifacts group — added lazily
        self._brain_group: Adw.PreferencesGroup | None = None

    # ---------------------------------------------------------------------- API

    def load(self, config: AgentConfig) -> None:
        """Populate the tab for the given agent config."""
        self._gemini_text_view = None
        self._gemini_path = None
        self._rebuild_gemini(config)
        self._rebuild_brain(config)

    # ------------------------------------------------------- GEMINI.md rendering

    def _rebuild_gemini(self, config: AgentConfig) -> None:
        """Clear and repopulate the GEMINI.md group."""
        # Remove existing children
        child = self._gemini_group.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            try:
                self._gemini_group.remove(child)
            except Exception:
                pass
            child = nxt

        if config.global_instructions is None:
            row = Adw.ActionRow(
                title="No GEMINI.md found",
                subtitle="~/.gemini/GEMINI.md not present",
            )
            row.add_css_class("dim-label")
            self._gemini_group.add(row)
            return

        gemini_path = config.global_instructions
        self._gemini_path = gemini_path

        try:
            content = gemini_path.read_text()
        except OSError:
            content = "(unreadable)"

        # Warning banner
        banner = Adw.Banner()
        banner.set_title("Global file \u2014 changes affect all Anti-Gravity sessions")
        banner.set_revealed(True)
        self._gemini_group.add(banner)

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
            rel = "~/" + str(gemini_path.relative_to(home))
        except ValueError:
            rel = str(gemini_path)

        hdr = Gtk.Label(label=f"Global  \u00b7  {rel}", xalign=0, hexpand=True)
        hdr.add_css_class("caption")
        hdr.add_css_class("heading")
        hdr_box.append(hdr)

        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.set_valign(Gtk.Align.CENTER)
        save_btn.connect("clicked", self._save_gemini)
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
        self._gemini_text_view = tv

        sw = Gtk.ScrolledWindow()
        sw.set_min_content_height(200)
        sw.set_max_content_height(600)
        sw.set_propagate_natural_height(True)
        sw.set_child(tv)
        block.append(sw)

        self._gemini_group.add(block)

    # --------------------------------------------------------- brain rendering

    def _rebuild_brain(self, config: AgentConfig) -> None:
        """Add or replace the brain artifacts group."""
        if self._brain_group is not None:
            try:
                self.remove(self._brain_group)
            except Exception:
                pass
            self._brain_group = None

        if not config.brain_dirs:
            return

        group = Adw.PreferencesGroup(title="Brain Artifacts")
        group.set_description("Conversation directories from Anti-Gravity brain")
        self._brain_group = group
        self.add(group)

        for brain_dir in config.brain_dirs:
            task_md = brain_dir / "task.md"
            subtitle = ""
            if task_md.exists():
                try:
                    lines = task_md.read_text().splitlines()
                    # Show the first non-empty line as preview
                    for line in lines:
                        stripped = line.strip()
                        if stripped:
                            subtitle = stripped[:120]
                            break
                except OSError:
                    pass

            row = Adw.ActionRow(
                title=brain_dir.name,
                subtitle=subtitle or str(brain_dir),
            )
            group.add(row)

    # -------------------------------------------------------------------- save

    def _save_gemini(self, _btn) -> None:
        if not self._gemini_path or not self._gemini_text_view:
            return
        buf = self._gemini_text_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        try:
            # Create .bak backup before writing
            shutil.copy2(self._gemini_path, self._gemini_path.with_suffix(".bak"))
            self._gemini_path.write_text(text)
            self._toast(f"Saved {self._gemini_path.name}")
        except Exception as e:
            self._toast(f"Error: {e}")

    def _toast(self, msg: str) -> None:
        win = self.get_root()
        if hasattr(win, "add_toast"):
            toast = Adw.Toast.new(msg)
            toast.set_timeout(0)
            win.add_toast(toast)
            GLib.timeout_add(1500, toast.dismiss)
