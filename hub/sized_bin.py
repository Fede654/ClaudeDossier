# Copyright (C) 2024, Manuel Genovés <manuel.genoves@gmail.com>
#
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
from gi.repository import Adw, GObject, Graphene, Gsk, Gtk

class ApostropheSizedBin(Adw.Bin):
    '''
    A container that exposes its size as properties
    '''

    __gtype_name__ = "ApostropheSizedBin"

    width = GObject.Property(type=int)
    height = GObject.Property(type=int)

    def __init__(self):
        super().__init__()
        self.set_layout_manager(None)
        self.queue_allocate()
        self.queue_resize()


    def do_size_allocate(self, width, height, baseline):
        if not self.get_child():
            return

        self.width = width
        self.height = height

        self.get_child().allocate(width, height, baseline, None)

    def do_measure(self, orientation, for_size):
        if not self.get_child():
            return (0, 0, -1, -1)

        return self.get_child().measure(orientation, for_size)
