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

from gettext import gettext as _

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Adw, Gio, GLib, GObject, Gtk


@Gtk.Template(resource_path='/io/fede/ClaudeDossier/ui/TableInput.ui')
class TableInput(Gtk.Overlay):

    __gtype_name__ = "TableInput"

    grid = Gtk.Template.Child()
    label = Gtk.Template.Child()

    rows = GObject.Property(type=int)
    columns = GObject.Property(type=int)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.connect("notify::rows", self._setup_grid)
        self.connect("notify::columns", self._setup_grid)

    def get_children(self):
        children = []
        child = self.grid.get_first_child()
        if child is not None:
            children.append(child)
            while child.get_next_sibling():
                child = child.get_next_sibling()
                children.append(child)
        return children

    def _setup_grid(self, *args, **kwargs):
        if len(self.get_children()) != self.rows*self.columns:
            for child in self.get_children():
                self.grid.remove(child)

            for row in range(self.rows):
                for column in range(self.columns):
                    button = Gtk.Button.new()

                    button.set_action_name("win.insert-table")
                    button.set_action_target_value(GLib.Variant("ai", [row+1, column+1]))

                    if row == 0 and column == self.columns - 1:
                        button.add_css_class("top-end")
                    if row == self.rows - 1 and column == 0:
                        button.add_css_class("bottom-start")

                    button.connect("notify::has-focus", self._hover_region)

                    controller = Gtk.EventControllerMotion.new()
                    controller.connect("enter", self._hover_region)
                    button.add_controller(controller)

                    self.grid.attach(button, column, row, 1, 1)

    def _hover_region(self, caller, *args, **kwargs):
        if isinstance(caller, Gtk.EventControllerMotion):
            button = caller.get_widget()
        else:
            button = caller

        button_column, button_row, _, _ = self.grid.query_child(button)

        for child in self.get_children():
            column, row, _, _ = self.grid.query_child(child)
            if column <= button_column and row <= button_row:
                child.add_css_class("hovered")
            else:
                child.remove_css_class("hovered")

        self.label.set_label(f"{button_row + 1} x {button_column + 1}")
