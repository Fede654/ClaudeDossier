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
from gi.repository import Adw, Gio, GLib, GObject, Graphene, Gsk, Gtk

class ApostropheMovableBin(Adw.Bin):

    __gtype_name__ = "ApostropheMovableBin"

    offset_x_ = 0

    @GObject.Property(type=float, default=0)
    def offset_x(self):
        return self.offset_x_

    @offset_x.setter
    def offset_x(self, value):
        self.offset_x_ = value
        self.queue_allocate()

    def __init__(self):
        super().__init__()
        self.set_layout_manager(None)

    def do_size_allocate(self, width, height, baseline):
        if not self.get_child():
            return
        transform = Gsk.Transform().translate(Graphene.Point().init(-self.offset_x*1, 0))

        self.get_child().allocate(width, height, baseline, transform)

    def do_measure(self, orientation, for_size):
        if not self.get_child():
            return(0, 0, -1, -1)

        child_size = self.get_child().measure(orientation, for_size)

        return (
            child_size.minimum,
            child_size.natural,
            child_size.minimum_baseline,
            child_size.natural_baseline
        )
