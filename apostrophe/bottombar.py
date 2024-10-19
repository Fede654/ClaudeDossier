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
from gi.repository import Adw, GLib, GObject, Gtk, Gsk, Graphene

from .settings import Settings


@Gtk.Template(resource_path='/org/gnome/gitlab/somas/Apostrophe/ui/BottomBar.ui')
class BottomBar(Gtk.Widget):
    __gtype_name__ = "ApostropheBottomBar"

    toolbar_ = None
    stats_ = None
    background_ = None

    toolbar_container = Gtk.Template.Child()
    stats_container = Gtk.Template.Child()
    background_container = Gtk.Template.Child()

    @GObject.Property(type=Gtk.Widget)
    def toolbar(self):
        return self.toolbar_

    @toolbar.setter
    def toolbar(self, value):
        self.toolbar_container.set_child(value)
        self.toolbar_ = value

    @GObject.Property(type=Gtk.Widget)
    def stats(self):
        return self.stats_

    @stats.setter
    def stats(self, value):
        self.stats_container.set_child(value)
        self.stats_ = value

    @GObject.Property(type=Gtk.Widget)
    def background(self):
        return self.background_

    @background.setter
    def background(self, value):
        self.background_container.set_child(value)
        self.background_ = value

    def __init__(self):
        super().__init__()

        self.queue_allocate()
        self.queue_resize()

    def do_size_allocate(self, width, height, baseline):

        toolbar_width = self.toolbar_container.measure(Gtk.Orientation.HORIZONTAL, -1).minimum
        toolbar_height = self.toolbar_container.measure(Gtk.Orientation.VERTICAL, -1).minimum

        stats_width = self.stats_container.measure(Gtk.Orientation.HORIZONTAL, -1).minimum
        stats_height = self.toolbar_container.measure(Gtk.Orientation.VERTICAL, -1).minimum

        stats_wide_width = self.stats.measure(Gtk.Orientation.HORIZONTAL, -1).minimum

        self.background_container.allocate(width, toolbar_height, baseline)

        if self.get_direction() == Gtk.TextDirection.LTR:
            offset = width - stats_width
            offset_transform = Gsk.Transform().translate(Graphene.Point().init(offset, 0))

            self.toolbar_container.allocate(toolbar_width, toolbar_height, baseline)
            self.stats_container.allocate(stats_width,stats_height, baseline, offset_transform)
        elif self.get_direction() == Gtk.TextDirection.RTL:
            offset = width - toolbar_width
            offset_transform = Gsk.Transform().translate(Graphene.Point().init(offset, 0))

            self.stats_container.allocate(stats_width,stats_height, baseline)
            self.toolbar_container.allocate(toolbar_width, toolbar_height, baseline, offset_transform)

        if toolbar_width + stats_wide_width > width:
            self.stats.buttons_stack.set_visible_child(self.stats.stats_button_short)
        else:
            self.stats.buttons_stack.set_visible_child(self.stats.stats_button)

    def do_measure(self, orientation, for_size):
        toolbar = self.toolbar_container.measure(orientation, -1)
        stats = self.stats.stats_button_short.measure(orientation, -1)

        if orientation == Gtk.Orientation.HORIZONTAL:
            return (
                toolbar.minimum + stats.minimum,
                toolbar.natural + stats.natural,
                toolbar.minimum_baseline,
                toolbar.natural_baseline
            )
        else:
            return (
                max(toolbar.minimum, stats.minimum),
                max(toolbar.natural, stats.natural),
                toolbar.minimum_baseline,
                toolbar.natural_baseline
            )
        
    def do_contains(self, x, y):
        bottombar_width = self.get_width()

        toolbar_width = self.toolbar_container.get_width()
        stats_width = self.stats_container.get_width()

        return y > 0 and ((x < toolbar_width or x > (bottombar_width - stats_width)) or self.toolbar.extra_toolbar_revealed)


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
    stats_button_short = Gtk.Template.Child()
    buttons_stack = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
