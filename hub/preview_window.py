# Copyright (C) 2024, Manuel Genovés <manuel.genoves@gmail.com>
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


import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Adw, Gio, Gtk

from gettext import gettext as _


@Gtk.Template(resource_path='/io/fede/ClaudeSessionHub/ui/PreviewWindow.ui')
class PreviewWindow(Adw.ApplicationWindow):

    __gtype_name__ = "ApostrophePreviewWindow"

    preview_box = Gtk.Template.Child()

    def __init__(self):
        super().__init__(application=Gio.Application.get_default(),
                         title=_("Preview"))
