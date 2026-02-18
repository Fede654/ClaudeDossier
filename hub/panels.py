# Copyright (C) 2022, Manuel Genovés <manuel.genoves@gmail.com>
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
import logging
from gettext import gettext as _

import gi

from hub.preview_layout_switcher import PreviewLayout
from hub.preview_window import PreviewWindow

gi.require_version('Gtk', '4.0')
from gi.repository import Adw, Gio, GLib, GObject, Graphene, Gsk, Gtk

LOGGER = logging.getLogger('hub')

@Gtk.Template(resource_path='/io/fede/ClaudeSessionHub/ui/Panels.ui')
class ApostrophePanels(Gtk.Widget, Gtk.Orientable):

    __gtype_name__ = "ApostrophePanels"

    __gsignals__ = {
        'close-panel-window': (GObject.SIGNAL_RUN_LAST, None, ()),
    }

    content_ = None
    panel_ = None
    layout_ = 0
    content_progress_ = 1
    panel_progress_ = 0
    orientation_ = None
    panels_collapsed_size = None

    previous_layout = None

    revealed_ = None
    reveal_duration = GObject.Property(type=float, default=250)
    content_tw = None
    panel_tw = None

    content_container = Gtk.Template.Child()
    panel_container = Gtk.Template.Child()
    separator = Gtk.Template.Child()

    panel_window = None
    panel_window_title = GObject.Property(type=str)

    @GObject.Property(type=Gtk.Orientation, default=Gtk.Orientation.VERTICAL)
    def orientation(self):
        return self.orientation_

    @orientation.setter
    def orientation(self, value):
        self.orientation_ = value
        self.queue_allocate()

    @GObject.Property(type=Gtk.Widget)
    def content(self):
        return self.content_

    @content.setter
    def content(self, value):
        self.content_container.set_child(value)
        self.content_ = value

    @GObject.Property(type=Gtk.Widget)
    def panel(self):
        return self.panel_

    @panel.setter
    def panel(self, value):
        self.panel_container.set_child(value)
        self.panel_ = value

    @GObject.Property(type=int, default=1)
    def layout(self):
        return self.layout_

    @layout.setter
    def layout(self, value):
        if self.layout == value:
            return

        self.layout_ = value

        # only move stuff around if the panel is revealed
        if self.revealed:
            self.relayout()
        self.previous_layout = self.layout

        # if layout is 0, we also set self.revealed to false
        # but we shouldn't get it here so we issue a warning as well
        if value == PreviewLayout.CLOSED:
            self.revealed = False
            LOGGER.warning("That layout shouldn't be set programatically. Try setting revealed to False instead.")

    @GObject.Property(type=bool, default=False)
    def revealed(self):
        return self.revealed_

    @revealed.setter
    def revealed(self, value):
        if self.revealed == value:
            return

        self.revealed_ = value

        if value == True:
            self.relayout(PreviewLayout.CLOSED, self.layout)
        else:
            self.relayout(self.layout, PreviewLayout.CLOSED)

    @GObject.Property(type=float, minimum=0, maximum=1)
    def content_progress(self):
        return self.content_progress_

    @content_progress.setter
    def content_progress(self, value):
        self.content_progress_ = value
        self.queue_resize()
        self.queue_allocate()

    @GObject.Property(type=float, minimum=0, maximum=1)
    def panel_progress(self):
        return self.panel_progress_

    @panel_progress.setter
    def panel_progress(self, value):
        self.panel_progress_ = value
        self.queue_resize()
        self.queue_allocate()

    def __init__(self):
        super().__init__()

        self.queue_allocate()
        self.queue_resize()

        self.previous_layout = self.layout

        self.content_tw = Adw.TimedAnimation.new(self, 0, 0, 0, Adw.PropertyAnimationTarget.new(self, "content-progress"))
        self.panel_tw = Adw.TimedAnimation.new(self, 0, 0, 0, Adw.PropertyAnimationTarget.new(self, "panel-progress"))
        self.panels_collapsed_size = (self.get_size(Gtk.Orientation.HORIZONTAL), self.get_size(Gtk.Orientation.VERTICAL))

    def do_size_allocate(self, width, height, baseline):
        if not self.content_progress + self.panel_progress >= 1:
            LOGGER.warning("The panel and content progress can't be both less than 1")

        if self.panel_progress + self.content_progress == 1:
            self.panels_collapsed_size = (self.get_size(Gtk.Orientation.HORIZONTAL), self.get_size(Gtk.Orientation.VERTICAL))

        orientation = self.get_orientation()
        cross_orientation = Gtk.Orientation.HORIZONTAL if orientation == Gtk.Orientation.VERTICAL else Gtk.Orientation.VERTICAL

        container_min_along = self.content_container.measure(orientation, -1).minimum
        separator_along = self.separator.measure(orientation, -1).minimum
        panel_min_along = self.panel.measure(orientation, -1).minimum

        panels_along = self.get_size(orientation)
        panels_across = self.get_size(cross_orientation)

        needed_along = container_min_along*2 + separator_along
        if panels_along >= needed_along:
            if self.content_progress + self.panel_progress == 1:
                container_along = panels_along
                panel_along = panels_along - separator_along

                container_offset = round((1 - self.content_progress) * container_along, 0)
                panel_offset = round((1 - self.panel_progress) * panel_along, 0)
            else:
                container_along = round(panels_along/2 + (1 - self.panel_progress)*panels_along/2, 0)
                panel_along = round(panels_along/2 + (1 - self.content_progress)*panels_along/2, 0)

                container_offset = round((1 - self.content_progress) * panels_along/2, 0)
                panel_offset = round((1 - self.panel_progress) * panels_along/2, 0)

        else:
            container_along = container_min_along + round((self.panels_collapsed_size[orientation] - container_min_along) * (2- self.panel_progress- self.content_progress), 0)
            panel_along = container_min_along + round((self.panels_collapsed_size[orientation] - container_min_along) * (2- self.content_progress- self.panel_progress), 0)

            container_offset = round(container_along * (1 - self.content_progress), 0)
            container_offset = round((1 - self.content_progress) * container_along, 0)
            panel_offset = round((1 - self.panel_progress) * panel_along, 0)


        # add the separator width to the offset of the panel we're hidding
        container_offset += separator_along if self.content_progress < 1 else 0
        panel_offset += separator_along if self.panel_progress < 1 else 0


        if orientation == Gtk.Orientation.HORIZONTAL:
            if self.get_direction() == Gtk.TextDirection.LTR:
                content_transform = Gsk.Transform().translate(Graphene.Point().init(-container_offset, 0))
                separator_transform = Gsk.Transform().translate(Graphene.Point().init(container_along - container_offset, 0))
                panel_transform = Gsk.Transform().translate(Graphene.Point().init(container_along - container_offset + separator_along, 0))
            elif self.get_direction() == Gtk.TextDirection.RTL:
                panel_transform = Gsk.Transform().translate(Graphene.Point().init(-panel_offset, 0))
                separator_transform = Gsk.Transform().translate(Graphene.Point().init(panel_along - panel_offset, 0))
                content_transform = Gsk.Transform().translate(Graphene.Point().init(panel_along - panel_offset + separator_along, 0))

            self.content_container.allocate(container_along, panels_across, -1, content_transform)
            self.separator.allocate(separator_along, panels_across, -1, separator_transform)
            self.panel_container.allocate(panel_along, panels_across, -1, panel_transform)
        else:
            content_transform = Gsk.Transform().translate(Graphene.Point().init(0, -container_offset))
            separator_transform = Gsk.Transform().translate(Graphene.Point().init(0, container_along - container_offset))
            panel_transform = Gsk.Transform().translate(Graphene.Point().init(0, container_along - container_offset + separator_along))

            self.content_container.allocate(panels_across, container_along, -1, content_transform)
            self.separator.allocate(panels_across, separator_along, -1, separator_transform)
            self.panel_container.allocate(panels_across, panel_along, -1, panel_transform)


    def do_measure(self, orientation, for_size):
        content = self.content_container.measure(orientation, for_size)
        panel = self.panel_container.measure(orientation, for_size)
        separator = self.separator.measure(orientation, for_size)

        same_orientation = self.get_orientation() == orientation

        # froze panel's width if we're in a transition to/from a two panel configuration
        if (self.content_tw.get_state() == Adw.AnimationState.PLAYING or self.panel_tw.get_state() == Adw.AnimationState.PLAYING) and\
            self.content_progress+self.panel_progress > 1:

            return (
                round(content.minimum
                      + (self.panels_collapsed_size[self.get_orientation()] - content.minimum)*(2-self.content_progress-self.panel_progress)*same_orientation
                      + content.minimum*(self.panel_progress + self.content_progress - 1)*same_orientation
                      + separator.minimum, 0),
                round(content.natural
                      + (self.panels_collapsed_size[self.get_orientation()] - content.natural)*(2-self.content_progress-self.panel_progress)*same_orientation
                      + content.natural*(self.panel_progress + self.content_progress - 1)*same_orientation
                      + separator.natural, 0),
                content.minimum_baseline,
                content.natural_baseline)
        else:
            return (
                round(content.minimum
                      + content.minimum*(self.panel_progress + self.content_progress - 1)*same_orientation
                      + separator.minimum*((self.panel_progress + self.content_progress) > 1), 0),
                round(content.natural
                      + content.natural*(self.panel_progress + self.content_progress - 1)*same_orientation
                      + separator.natural*((self.panel_progress + self.content_progress) > 1), 0),
                content.minimum_baseline,
                content.natural_baseline)

    def do_root(self):
        Gtk.Widget.do_root(self)
        if not self.content_container.get_parent():
            self.content_container.set_parent(self)

        if not self.panel_container.get_parent():
            self.panel_container.set_parent(self)

        if not self.separator.get_parent():
            self.separator.set_parent(self)

    def do_unroot(self):
        self.content_container.unparent()
        self.panel_container.unparent()
        self.separator.unparent()

        Gtk.Widget.do_unroot(self)

    def do_dispose(self):
        self.content_container = None
        self.panel_container = None
        self.separator = None

        Gtk.Widget.do_dispose(self)

    layouts = {
        PreviewLayout.CLOSED: {
            'content': 1,
            'panel': 0,
            'orientation': Gtk.Orientation.HORIZONTAL,
            'detached': False
        },
        PreviewLayout.HALF_WIDTH: {
            'content': 1,
            'panel': 1,
            'orientation': Gtk.Orientation.HORIZONTAL,
            'detached': False
        },
        PreviewLayout.FULL_WIDTH: {
            'content': 0,
            'panel': 1,
            'orientation': Gtk.Orientation.HORIZONTAL,
            'detached': False
        },
        PreviewLayout.HALF_HEIGHT: {
            'content': 1,
            'panel': 1,
            'orientation': Gtk.Orientation.VERTICAL,
            'detached': False
        },
        PreviewLayout.WINDOWED: {
            'content': 1,
            'panel': 0,
            'orientation': Gtk.Orientation.HORIZONTAL,
            'detached': True
        }
    }

    def relayout(self, from_layout=None, to_layout=None):
        # we want to be able to hook any value, for example to 
        # manually relayout when showing and hidding the panel
        if from_layout is None:
            from_layout = self.previous_layout
        if to_layout is None:
            to_layout = self.layout

        if self.layouts[from_layout]['detached']:
            self.reatach_panel()
            from_layout = PreviewLayout.CLOSED

        if self.layouts[to_layout]['detached']:
            self.animate_to_layout(from_layout, PreviewLayout.CLOSED, self.detach_panel)

        elif self.layouts[from_layout]['orientation'] != self.layouts[to_layout]['orientation']:
            # move to layout PreviewLayout.CLOSED
            self.animate_to_layout(from_layout, PreviewLayout.CLOSED, self.change_orientation, to_layout)
        else:
            self.animate_to_layout(from_layout, to_layout, None)

    def change_orientation(self, *args, **kwargs):
        # we pop to_layout from the cb data if it exists
        to_layout = args[-1] if isinstance(args[-1], int) else self.layout

        self.set_orientation(self.layouts[to_layout]['orientation'])
        self.animate_to_layout(PreviewLayout.CLOSED, to_layout, None)

    def detach_panel(self, *args, **kwarg):
        self.panel_window = PreviewWindow()
        self.panel.unparent()
        self.panel_window.preview_box.append(self.panel)
        self.panel_window.show()
        self.bind_property("panel_window_title", self.panel_window, "title")
        self.panel_window.connect("close-request", self.on_panel_window_closed)

    def on_panel_window_closed(self, *args, **kwargs):
        self.emit("close-panel-window")

    def reatach_panel(self):
        self.panel_window.preview_box.remove(self.panel)
        self.panel.unparent()
        self.panel.set_parent(self.panel_container)
        self.panel_window.destroy()
        self.panel_window = None

        self.queue_allocate()
        self.queue_resize()

    def animate_to_layout(self, from_layout, to_layout, callback = None, cb_data = None):
        callback_hooked = False
        if from_layout == to_layout:
            if callback:
                callback(cb_data)

        if self.layouts[from_layout]['content'] != self.layouts[to_layout]['content']:
            content_target = Adw.PropertyAnimationTarget.new(self, "content-progress")
            self.content_tw = Adw.TimedAnimation.new(self, 
                                                self.layouts[from_layout]['content'],
                                                self.layouts[to_layout]['content'],
                                                self.reveal_duration, content_target)
            if callback:
                self.content_tw.connect("done", callback, cb_data)
                callback_hooked = True

            self.content_tw.play()

        if self.layouts[from_layout]['panel'] != self.layouts[to_layout]['panel']:
            panel_target = Adw.PropertyAnimationTarget.new(self, "panel-progress")
            self.panel_tw = Adw.TimedAnimation.new(self, 
                                                self.layouts[from_layout]['panel'],
                                                self.layouts[to_layout]['panel'],
                                                self.reveal_duration, panel_target)
            if callback and not callback_hooked:
                self.panel_tw.connect("done", callback, cb_data)
            self.panel_tw.play()
