"""Project metadata page + CLAUDE.md inheritance chain viewer."""
from __future__ import annotations
from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk

from hub.data.session_scanner import ProjectInfo


def _claude_chain(project_path: str) -> list[tuple[str, bool]]:
    """Walk up from project_path to $HOME, then ~/.claude/CLAUDE.md."""
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



class ProjectPage(Adw.PreferencesPage):
    __gtype_name__ = 'ProjectPage'

    def __init__(self):
        super().__init__()
        self._project = None
        self._text_view = None  # created dynamically for the project entry
        self._build()

    def _build(self):
        meta = Adw.PreferencesGroup(title='Project')
        self._path_row = Adw.ActionRow(title='Path')
        self._sessions_row = Adw.ActionRow(title='Sessions')
        self._active_row = Adw.ActionRow(title='Last active')
        for row in (self._path_row, self._sessions_row, self._active_row):
            meta.add(row)
        self.add(meta)

        eff_group = Adw.PreferencesGroup(title='CLAUDE.md Chain')
        eff_group.set_description('Load order: global → project (only present files shown)')
        self._effective_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._effective_box.set_margin_top(4)
        self._effective_box.set_margin_bottom(8)
        self._effective_box.set_margin_start(6)
        self._effective_box.set_margin_end(6)
        eff_group.add(self._effective_box)
        self.add(eff_group)

    def load(self, project: ProjectInfo) -> None:
        self._project = project
        self._text_view = None
        path_sub = project.original_path
        if not project.exists_on_disk:
            path_sub += '  ⚠ directory not found'
        self._path_row.set_subtitle(path_sub)
        self._sessions_row.set_subtitle(str(len(project.sessions)))
        la = project.last_active
        self._active_row.set_subtitle(
            la.strftime('%Y-%m-%d %H:%M') if la.year > 1 else '—'
        )

        self._rebuild_effective(project.original_path)

    def _rebuild_effective(self, project_path: str) -> None:
        child = self._effective_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._effective_box.remove(child)
            child = nxt

        chain = _claude_chain(project_path)
        existing = [(p, exists) for p, exists in reversed(chain) if exists]

        if not existing:
            lbl = Gtk.Label(label='No CLAUDE.md files found in chain', xalign=0)
            lbl.add_css_class('dim-label')
            lbl.set_margin_start(8)
            lbl.set_margin_top(8)
            self._effective_box.append(lbl)
            return

        home = Path.home()
        proj = Path(project_path)

        for idx, (path_str, _) in enumerate(existing):
            p = Path(path_str)
            is_project = (p.parent == proj)
            is_last = (idx == len(existing) - 1)

            if p == home / '.claude' / 'CLAUDE.md':
                role = 'Global  ·  ~/.claude/CLAUDE.md'
            elif is_project:
                rel = '~/' + str(p.relative_to(home)) if p.is_relative_to(home) else path_str
                role = f'Project  ·  {rel}'
            else:
                try:
                    rel = '~/' + str(p.relative_to(home))
                except ValueError:
                    rel = path_str
                role = rel

            try:
                content = p.read_text()
            except OSError:
                content = '(unreadable)'

            block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            block.add_css_class('card')
            block.set_margin_bottom(2)

            # Header row: role label + (Save button if editable)
            hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            hdr_box.set_margin_start(10)
            hdr_box.set_margin_top(8)
            hdr_box.set_margin_end(10)
            hdr_box.set_margin_bottom(6)

            hdr = Gtk.Label(label=role, xalign=0, hexpand=True)
            hdr.add_css_class('caption')
            hdr.add_css_class('heading')
            hdr_box.append(hdr)

            if is_last:
                save_btn = Gtk.Button(label='Save')
                save_btn.add_css_class('suggested-action')
                save_btn.set_valign(Gtk.Align.CENTER)
                save_btn.connect('clicked', self._save)
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
                # Project block is editable; keep reference for _save()
                self._text_view = tv
            else:
                tv.set_editable(False)
                tv.set_cursor_visible(False)

            sw = Gtk.ScrolledWindow()
            sw.set_min_content_height(480)
            sw.set_max_content_height(1280)
            sw.set_propagate_natural_height(True)
            sw.set_child(tv)
            block.append(sw)

            self._effective_box.append(block)

    def _save(self, _):
        if not self._project or not self._text_view:
            return
        buf = self._text_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        target = Path(self._project.original_path) / 'CLAUDE.md'
        try:
            target.write_text(text)
            win = self.get_root()
            if hasattr(win, 'add_toast'):
                win.add_toast(Adw.Toast.new(f'Saved {target.name}'))
        except Exception as e:
            win = self.get_root()
            if hasattr(win, 'add_toast'):
                win.add_toast(Adw.Toast.new(f'Error: {e}'))
