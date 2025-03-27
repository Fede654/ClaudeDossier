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

import collections
from datetime import datetime
from gettext import gettext as _

import gi

from apostrophe.movable_bin import ApostropheMovableBin
from apostrophe.stats_handler import StatsHandler

gi.require_version('Gtk', '4.0')
from gi.repository import Adw, GLib, GObject, Gtk

from apostrophe.bottombar import BottomBar, Statsbar, Toolbar
from apostrophe.text_view_scroller import TextViewScroller

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
    movablebin = Gtk.Template.Child()
    sizehandler = Gtk.Template.Child()

    hemingway_attempts = collections.deque(4*[datetime.min], 4)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.settings = Settings.new()

        # Setup stats counter
        self.stats_handler = StatsHandler(self.stats_revealer.stats_button, self.stats_revealer.stats_button_short, self.textview)

        # Initialize bottombar background
        self.reveal_toolbar()

        self.textview.get_buffer().connect('attempted-hemingway', self.on_attempted_hemingway)

        self.textview.scroller = TextViewScroller(self.textview, self.scrolledwindow)
        self.scrolledwindow.get_vadjustment().connect("changed",
                                            self.textview._on_vadjustment_changed)
        self.scrolledwindow.get_vadjustment().connect("value-changed",
                                            self.textview._on_vadjustment_changed)

        self.sizehandler.set_size_request(360, 200)
        self.breakpoints = []
        self.set_breakpoints()
        self.textview.connect("notify::bigger-text", self.set_breakpoints)

    @Gtk.Template.Callback()
    def reveal_toolbar(self, *_args):
        if self.toolbar_revealer.extra_toolbar_revealed:
            self.background.add_css_class('shown')
            self.background.set_can_target(True)
            self.toolbar_revealer.show_extra_controls_button.add_css_class('active')
        else:
            self.background.remove_css_class('shown')
            self.background.set_can_target(False)
            self.toolbar_revealer.show_extra_controls_button.remove_css_class('active')

    @Gtk.Template.Callback()
    def reveal_bottombar(self, *args):
        if not self.stats_revealer.get_reveal_child():
            self.stats_revealer.set_reveal_child(True)
            self.stats_revealer.set_halign(Gtk.Align.END)

        if not self.toolbar_revealer.get_reveal_child():
            self.toolbar_revealer.set_reveal_child(True)

        if not self.background.get_reveal_child():
            self.background.set_reveal_child(True)

    def set_breakpoints(self, *args, **kwargs):
        if self.breakpoints:
            for breakpoint in self.breakpoints:
                self.sizehandler.remove_breakpoint(breakpoint)
            self.breakpoints = []

        # dict with all breakpoints and their setters
        # any setter is applied to smaller breakpoints as well
        # all breakpoints trigger textview.update_font_size
        breakpoints = {}

        # breakpoints for font sizes
        for font_size in self.textview._get_font_sizes():
            # at this point self.line_chars should still be the default
            # we rely on that.
            width = self.textview.get_min_width(font_size)
            breakpoints.update({width: None})

        # store in a set all setters so they're applied to smaller breakpoints
        props_to_apply = set()
        for width, props in sorted(breakpoints.items(), reverse=True):
            condition = Adw.BreakpointCondition.new_length(Adw.BreakpointConditionLengthType.MAX_WIDTH, width, Adw.LengthUnit.PX)
            breakpoint = Adw.Breakpoint.new(condition)
            breakpoint.connect("apply", self.textview.update_font_size)
            breakpoint.connect("unapply", self.textview.update_font_size)
            if props:
                for prop in props:
                    props_to_apply.add(prop)
            if props_to_apply:
                for prop in props_to_apply:
                    breakpoint.add_setter(*prop)
            self.breakpoints.append(breakpoint)
            self.sizehandler.add_breakpoint(breakpoint)


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

    def on_attempted_hemingway(self, *args):
        # log the time into a list with max length of 4
        # then check if the time differences are small enough
        # to show the help popover again
        self.hemingway_attempts.appendleft(datetime.now())
        if (self.hemingway_attempts[0] - self.hemingway_attempts[3]).seconds <= 70:
            self.settings.set_int("hemingway-toast-count", 0)
            self.activate_action("win.show_hemingway_toast")
            pass

        spring_params = Adw.SpringParams.new(0.5, 50, 30000)
        target = Adw.PropertyAnimationTarget.new(self.movablebin, "offset-x")
        hemingway_animation = Adw.SpringAnimation.new(self, 0, 0, spring_params, target)
        hemingway_animation.set_initial_velocity(100)
        hemingway_animation.set_epsilon(0.01)
        hemingway_animation.play()
