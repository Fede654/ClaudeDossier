# Copyright (C) 2023, Manuel Genovés <manuel.genoves@gmail.com>
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
# END LICENSE
"""Manage the bottombar. It comprises the toolbar and the statsbar
"""

from gettext import gettext as _

import gi

from apostrophe.stats_handler import StatsHandler

gi.require_version('Gtk', '4.0')
from gi.repository import Adw, GLib, GObject, Gtk

from apostrophe.bottombar import Statsbar, Toolbar

from .settings import Settings


@Gtk.Template(resource_path='/org/gnome/gitlab/somas/Apostrophe/ui/Editor.ui')
class Editor(Adw.Bin):

    __gtype_name__ = "Editor"

    scrolledwindow = Gtk.Template.Child()
    toolbar_revealer = Gtk.Template.Child()
    toast_overlay = Gtk.Template.Child()
    stats_revealer = Gtk.Template.Child()
    background = Gtk.Template.Child()
    textview = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Setup stats counter
        self.stats_handler = StatsHandler(self.stats_revealer.stats_button, self.textview)

        # Initialize bottombar background
        self.reveal_toolbar()

    @Gtk.Template.Callback()
    def reveal_toolbar(self, *_args):
        if self.toolbar_revealer.extra_toolbar_revealed:
            self.background.get_style_context().add_class('shown')
            self.background.set_can_target(True)
            self.toolbar_revealer.show_extra_controls_button.get_style_context().add_class('active')
        else:
            self.background.get_style_context().remove_class('shown')
            self.background.set_can_target(False)
            self.toolbar_revealer.show_extra_controls_button.get_style_context().remove_class('active')

    @Gtk.Template.Callback()
    def reveal_bottombar(self, *args):
        if not self.stats_revealer.get_reveal_child():
            self.stats_revealer.set_reveal_child(True)
            self.stats_revealer.set_halign(Gtk.Align.END)

        if not self.toolbar_revealer.get_reveal_child():
            self.toolbar_revealer.set_reveal_child(True)

        if not self.background.get_reveal_child():
            self.background.set_reveal_child(True)

    def hide_bottombar(self):
        if self.stats_revealer.get_reveal_child():
            self.stats_revealer.set_reveal_child(False)
            self.stats_revealer.set_halign(Gtk.Align.FILL)

        if self.toolbar_revealer.get_reveal_child():
            self.toolbar_revealer.set_reveal_child(False)

        if self.background.get_reveal_child():
            self.background.set_reveal_child(False)

    def update_default_stat(self):
        self.stats_handler.update_default_stat()
