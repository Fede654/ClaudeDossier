# Copyright (C) 2022, Manuel Genovés <manuel.genoves@gmail.com>
#               2019, Wolf Vollprecht <w.vollprecht@gmail.com>
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

"""this dialog adjusts values in gsettings
"""
import webbrowser

import gi

gi.require_version('Gtk', '4.0')
import logging

from gi.repository import Adw, Gio, GObject, Gtk
from hub.settings import Settings

logger = logging.getLogger('hub')

@Gtk.Template(resource_path='/io/fede/ClaudeDossier/ui/Preferences.ui')
class ApostrophePreferencesDialog(Adw.PreferencesDialog):

    __gtype_name__ = "ApostrophePreferencesDialog"

    enable_claude_row = Gtk.Template.Child()
    enable_codex_row = Gtk.Template.Child()
    enable_antigravity_row = Gtk.Template.Child()

    settings = Settings.new()

    def __init__(self):
        super().__init__()

        self.settings.bind("enable-claude",
                           self.enable_claude_row,
                           "active",
                           Gio.SettingsBindFlags.DEFAULT)

        self.settings.bind("enable-codex",
                           self.enable_codex_row,
                           "active",
                           Gio.SettingsBindFlags.DEFAULT)

        self.settings.bind("enable-antigravity",
                           self.enable_antigravity_row,
                           "active",
                           Gio.SettingsBindFlags.DEFAULT)
