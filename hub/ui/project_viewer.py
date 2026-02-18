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
        self._build()

    def _build(self):
        meta = Adw.PreferencesGroup(title='Project')
        self._path_row = Adw.ActionRow(title='Path')
        self._disk_row = Adw.ActionRow(title='Directory on disk')
        self._sessions_row = Adw.ActionRow(title='Sessions')
        self._active_row = Adw.ActionRow(title='Last active')
        for row in (self._path_row, self._disk_row, self._sessions_row, self._active_row):
            meta.add(row)
        self.add(meta)

        self._chain_group = Adw.PreferencesGroup(title='CLAUDE.md Inheritance')
        self.add(self._chain_group)

        editor_group = Adw.PreferencesGroup(title='Project CLAUDE.md')
        self._editor_expander = Adw.ExpanderRow(title='Edit project CLAUDE.md')
        self._text_view = Gtk.TextView()
        self._text_view.set_monospace(True)
        self._text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._text_view.set_top_margin(8)
        self._text_view.set_left_margin(8)
        sw = Gtk.ScrolledWindow()
        sw.set_min_content_height(180)
        sw.set_child(self._text_view)
        self._editor_expander.add_row(sw)
        save_btn = Gtk.Button(label='Save')
        save_btn.add_css_class('suggested-action')
        save_btn.connect('clicked', self._save)
        self._editor_expander.add_action_widget(save_btn)
        editor_group.add(self._editor_expander)
        self.add(editor_group)

    def load(self, project: ProjectInfo) -> None:
        self._project = project
        self._path_row.set_subtitle(project.original_path)
        self._disk_row.set_subtitle('Exists' if project.exists_on_disk else 'Not found on disk')
        self._sessions_row.set_subtitle(str(len(project.sessions)))
        la = project.last_active
        self._active_row.set_subtitle(
            la.strftime('%Y-%m-%d %H:%M') if la.year > 1 else '—'
        )

        # Rebuild chain rows — remove old rows first
        child = self._chain_group.get_first_child()
        while child:
            next_c = child.get_next_sibling()
            if isinstance(child, Adw.ActionRow):
                self._chain_group.remove(child)
            child = next_c

        for path_str, exists in _claude_chain(project.original_path):
            row = Adw.ActionRow(title=Path(path_str).name)
            row.set_subtitle(path_str)
            row.add_suffix(Gtk.Image.new_from_icon_name(
                'emblem-ok-symbolic' if exists else 'dialog-question-symbolic'
            ))
            self._chain_group.add(row)

        # Load project CLAUDE.md into editor
        proj_md = Path(project.original_path) / 'CLAUDE.md'
        self._text_view.get_buffer().set_text(
            proj_md.read_text() if proj_md.exists() else ''
        )

    def _save(self, _):
        if not self._project:
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
