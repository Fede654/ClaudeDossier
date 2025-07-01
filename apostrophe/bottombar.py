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
from gi.repository import Adw, GLib, GObject, Gtk, Gsk, Graphene, Gio

from .settings import Settings


@Gtk.Template(resource_path='/org/gnome/gitlab/somas/Apostrophe/ui/BottomBar.ui')
class BottomBar(Gtk.Widget):
    __gtype_name__ = "ApostropheBottomBar"

    toolbar_ = None
    toolbar_narrow_ = None
    stats_ = None
    background_ = None

    toolbars_container = Gtk.Template.Child()
    stats_container = Gtk.Template.Child()
    background_container = Gtk.Template.Child()

    narrow = GObject.Property(type=bool, default=False)

    @GObject.Property(type=Gtk.Widget)
    def toolbar(self):
        return self.toolbar_

    @toolbar.setter
    def toolbar(self, value):
        self.toolbars_container.add_named(value, "toolbar")
        self.toolbar_ = value

    @GObject.Property(type=Gtk.Widget)
    def toolbar_narrow(self):
        return self.toolbar_narrow_

    @toolbar_narrow.setter
    def toolbar_narrow(self, value):
        self.toolbars_container.add_named(value, "toolbar_narrow")
        self.toolbar_narrow_ = value

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
        toolbar_width = self.toolbars_container.measure(Gtk.Orientation.HORIZONTAL, -1).minimum
        toolbar_height = self.toolbars_container.measure(Gtk.Orientation.VERTICAL, -1).minimum

        stats_wide_width = self.stats.stats_button.measure(Gtk.Orientation.HORIZONTAL, -1).minimum

        if (toolbar_width + stats_wide_width) >= width or self.narrow:
            self.stats.buttons_stack.set_visible_child(self.stats.stats_button_short)
        else:
            self.stats.buttons_stack.set_visible_child(self.stats.stats_button)

        bg_min_w = self.background_container.measure(Gtk.Orientation.HORIZONTAL, -1).minimum
        bg_min_h = self.background_container.measure(Gtk.Orientation.HORIZONTAL, -1).minimum

        stats_width = self.stats_container.measure(Gtk.Orientation.HORIZONTAL, -1).minimum
        stats_height = self.toolbars_container.measure(Gtk.Orientation.VERTICAL, -1).minimum

        self.background_container.allocate(max(width, bg_min_w), max(toolbar_height, bg_min_h), baseline)

        if self.get_direction() == Gtk.TextDirection.LTR:
            offset = width - stats_width
            offset_transform = Gsk.Transform().translate(Graphene.Point().init(offset, 0))

            self.toolbars_container.allocate(toolbar_width, toolbar_height, baseline)
            self.stats_container.allocate(stats_width, stats_height, baseline, offset_transform)
        elif self.get_direction() == Gtk.TextDirection.RTL:
            offset = width - toolbar_width
            offset_transform = Gsk.Transform().translate(Graphene.Point().init(offset, 0))

            self.stats_container.allocate(stats_width, stats_height, baseline)
            self.toolbars_container.allocate(toolbar_width, toolbar_height, baseline, offset_transform)


    def do_measure(self, orientation, for_size):
        toolbar = self.toolbars_container.measure(orientation, -1)
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

        toolbar_width = self.toolbars_container.get_width()
        stats_width = self.stats_container.get_width()

        return y > 0 and (
            (x < toolbar_width or 
             x > (bottombar_width - stats_width)) or 
             (self.toolbar.extra_toolbar_revealed and not self.narrow))

    def get_expanded_width(self):
        toolbar_size = self.toolbar.toolbar_extra_revealer.get_child().measure(Gtk.Orientation.HORIZONTAL, -1)
        show_button_size = self.toolbar.show_extra_controls_button.measure(Gtk.Orientation.HORIZONTAL, -1)
        stats_size = self.stats.stats_button_short.measure(Gtk.Orientation.HORIZONTAL, -1)

        return toolbar_size.minimum + show_button_size.minimum + stats_size.minimum

    def do_dispose(self):
        self.toolbar = None
        self.toolbar_narrow = None
        self.stats = None
        self.background = None

        Gtk.Widget.do_dispose(self)

@Gtk.Template(resource_path='/org/gnome/gitlab/somas/Apostrophe/ui/Toolbar.ui')
class Toolbar(Gtk.Revealer):

    __gtype_name__ = "Toolbar"

    show_extra_controls_button = Gtk.Template.Child()
    toolbar_extra_revealer = Gtk.Template.Child()
    show_extra_controls_button = Gtk.Template.Child()

    extra_toolbar_revealed = GObject.Property(type=bool, default=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.settings = Settings.new()
        self.connect("notify::extra-toolbar-revealed", self.on_toolbar_reveal)
        self.settings.bind("toolbar-active", self, "extra-toolbar-revealed",
            Gio.SettingsBindFlags.DEFAULT|Gio.SettingsBindFlags.GET_NO_CHANGES)

    def on_toolbar_reveal(self, toolbar, revealed):
        if self.extra_toolbar_revealed:
            self.show_extra_controls_button.set_tooltip_text(_("Hide Toolbar"))
        else:
            self.show_extra_controls_button.set_tooltip_text(_("Show Toolbar"))

@Gtk.Template(resource_path='/org/gnome/gitlab/somas/Apostrophe/ui/ToolbarNarrow.ui')
class ToolbarNarrow(Gtk.Revealer):

    __gtype_name__ = "ToolbarNarrow"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

@Gtk.Template(resource_path='/org/gnome/gitlab/somas/Apostrophe/ui/Statsbar.ui')
class Statsbar(Gtk.Revealer):

    __gtype_name__ = "Statsbar"

    stats_button = Gtk.Template.Child()
    stats_button_short = Gtk.Template.Child()
    buttons_stack = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # make the stack report the biggest size while transitioning to not have jumps when allocating
        self.buttons_stack.bind_property("transition-running", self.buttons_stack, "hhomogeneous")
