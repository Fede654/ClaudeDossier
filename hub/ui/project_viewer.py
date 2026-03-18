"""Project metadata + multi-agent configuration tabs."""
from __future__ import annotations

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk

from hub.data.session_scanner import ProjectInfo


class ProjectPage(Gtk.Box):
    __gtype_name__ = 'ProjectPage'

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._project = None
        self._tabs = {}

        # Metadata header (always visible)
        meta = Adw.PreferencesGroup(title='Project')
        meta.set_margin_start(12)
        meta.set_margin_end(12)
        meta.set_margin_top(12)
        self._path_row = Adw.ActionRow(title='Path')
        self._sessions_row = Adw.ActionRow(title='Sessions')
        self._active_row = Adw.ActionRow(title='Last active')
        for row in (self._path_row, self._sessions_row, self._active_row):
            meta.add(row)
        self.append(meta)

        # ViewStack for agent tabs
        self._stack = Adw.ViewStack()
        self._stack.set_vexpand(True)

        # Wrap stack in a ScrolledWindow so tab content scrolls
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        sw.set_child(self._stack)
        self.append(sw)

        # ViewSwitcherBar at bottom
        self._switcher = Adw.ViewSwitcherBar()
        self._switcher.set_stack(self._stack)
        self._switcher.set_reveal(True)
        self.append(self._switcher)

    def load(self, project: ProjectInfo) -> None:
        self._project = project

        # Update metadata
        path_sub = project.original_path
        if not project.exists_on_disk:
            path_sub += '  (directory not found)'
        self._path_row.set_subtitle(path_sub)
        self._sessions_row.set_subtitle(str(len(project.sessions)))
        la = project.last_active
        self._active_row.set_subtitle(
            la.strftime('%Y-%m-%d %H:%M') if la.year > 1 else '\u2014'
        )

        # Discover agent configs
        from hub.data.agent_config import discover_agent_configs
        configs = discover_agent_configs(project.original_path, project.sessions)

        # Clear existing tabs
        while True:
            page = self._stack.get_first_child()
            if page is None:
                break
            self._stack.remove(page)
        self._tabs.clear()

        # Build tabs for agents with data
        for config in configs:
            if not config.has_data:
                continue

            if config.agent == 'claude':
                from hub.ui.claude_tab import ClaudeTab
                tab = ClaudeTab()
                tab.load(project.original_path, config)
                self._stack.add_titled_with_icon(
                    tab, 'claude', 'Claude', 'document-edit-symbolic')

            elif config.agent == 'codex':
                from hub.ui.codex_tab import CodexTab
                tab = CodexTab()
                tab.load(project.original_path, config)
                self._stack.add_titled_with_icon(
                    tab, 'codex', 'Codex', 'utilities-terminal-symbolic')

            elif config.agent == 'antigravity':
                from hub.ui.antigravity_tab import AntiGravityTab
                tab = AntiGravityTab()
                tab.load(config)
                self._stack.add_titled_with_icon(
                    tab, 'antigravity', 'Anti-Gravity', 'weather-clear-symbolic')

            self._tabs[config.agent] = tab

        # Hide switcher if only one tab
        self._switcher.set_reveal(len(self._tabs) > 1)
