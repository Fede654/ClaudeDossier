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

from .settings import Settings


@Gtk.Template(resource_path='/org/gnome/gitlab/somas/Apostrophe/ui/Toolbar.ui')
class Toolbar(Gtk.Revealer):

    __gtype_name__ = "Toolbar"

    show_extra_controls_button = Gtk.Template.Child()

    extra_toolbar_revealed = GObject.Property(type=bool, default=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.settings = Settings.new()
        self.extra_toolbar_revealed = self.settings.get_boolean("toolbar-active")

@Gtk.Template(resource_path='/org/gnome/gitlab/somas/Apostrophe/ui/Statsbar.ui')
class Statsbar(Gtk.Revealer):

    __gtype_name__ = "Statsbar"

    stats_button = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
