# Copyright (C) 2024-2025 Sophie Herold
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
"""Show generic errors with an optional detailed error description in a textview
"""

from gettext import gettext as _

import gi


gi.require_version('Gtk', '4.0')
from gi.repository import Adw, Gtk


@Gtk.Template(resource_path='/io/fede/ClaudeDossier/ui/DetailedError.ui')
class DetailedError(Adw.Dialog):
    __gtype_name__ = "DetailedError"

    description = Gtk.Template.Child()
    message = Gtk.Template.Child()

    def __init__(self, description:None|str, message: str, **kwargs):
        super().__init__(**kwargs)
        if description:
            self.description.set_label(description)
        self.message.get_buffer().set_text(message)

    @Gtk.Template.Callback()
    def copy_error_message(self, *args, **kwargs):
        clipboard = self.get_clipboard()
        buffer = self.message.get_buffer()
        start, end = buffer.get_bounds()
        clipboard.set(self.message.get_buffer().get_text(start, end, False))

    @Gtk.Template.Callback()
    def report_issue(self, *args, **kwargs):
        Gtk.UriLauncher.new("https://gitlab.gnome.org/World/apostrophe/-/issues").launch(self.get_root(), None, None, None)