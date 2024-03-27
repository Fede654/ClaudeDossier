# Copyright (C) 2024, Manuel Genovés <manuel.genoves@gmail.com>
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

import logging

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Adw, GObject, Gtk, GtkSource

LOGGER = logging.getLogger('apostrophe')

@Gtk.Template(resource_path='/org/gnome/gitlab/somas/Apostrophe/ui/SearchBar.ui')
class ApostropheSearchBar(Adw.Bin):
    """
    Adds (regex) search and replace functionality to
    apostrophe
    """
    __gtype_name__ = "ApostropheSearchBar"

    replace_mode_enabled = GObject.property(type=bool, default=False)
    search_mode_enabled = GObject.property(type=bool, default=False)
    searchbar = Gtk.Template.Child()
    search_entry = Gtk.Template.Child()
    regex = Gtk.Template.Child()
    case_sensitive = Gtk.Template.Child()
    replace_entry = Gtk.Template.Child()

    @GObject.Property(type=bool, default=False)
    def can_move(self):
        return self.search_context.get_occurrences_count() > 0

    @GObject.Property(type=bool, default=False)
    def can_replace(self):
        if self.textbuffer.get_has_selection():
            start, end = self.textbuffer.get_selection_bounds()
            return self.can_move and self.textbuffer.get_has_selection() and self.search_context.get_occurrence_position(start, end) > 0
        else:
            return False
    
    @GObject.Property(type=bool, default=False)
    def can_replace_all(self):
        return self.can_move

    def __init__(self):
        self.textbuffer = None
        self.search_settings = None
        self.search_context = None

        # contruct a paintable to check size changes
        self.paintable = Gtk.WidgetPaintable.new(self)
        self.paintable.connect("invalidate-size", self.update_textview_margin)

        self.connect("notify::search-mode-enabled", self.search_enabled)
        self.connect("notify::replace-mode-enabled", self.replace_enabled)

    def attach(self, textview):
        self.textview = textview
        self.textbuffer = self.textview.get_buffer()
        self.search_settings = GtkSource.SearchSettings.new()
        self.search_context = GtkSource.SearchContext.new(self.textbuffer, self.search_settings)

        self.highlight = self.textbuffer.create_tag('search_highlight',
                                                    background="yellow")
        self.search_context.connect("notify::occurrences-count", self._on_notify_occurrences_count)

        self.search_settings.set_wrap_around(True)

        self.regex.bind_property("active", self.search_settings, "regex-enabled")
        self.case_sensitive.bind_property("active", self.search_settings, "case-sensitive")

    def search_enabled(self, *args, **kwargs):
        if self.searchbar.get_search_mode():
            self.textbuffer = self.textview.get_buffer()
            if self.textbuffer.get_has_selection():
                self.search_entry.set_text(self.textbuffer.get_slice(*self.textbuffer.get_selection_bounds(), False))
            self.search_entry.grab_focus()
            self.search_entry.select_region(0, -1)
            self.search_context.set_highlight(True)
        else:
            self.replace_mode_enabled = False
            self.textview.grab_focus()
            self.search_context.set_highlight(False)

    def replace_enabled(self, _widget, _data):
        if self.replace_mode_enabled and not self.search_mode_enabled:
            self.search_mode_enabled = True

    @Gtk.Template.Callback()
    def search_entry_changed(self, _widget=None, _data=None, scroll=True):
        self.search_settings.set_search_text(self.search_entry.get_text())

    def select_search_occurrence(self, start, end):
        self.textbuffer.select_range(start, end)

        insert = self.textbuffer.get_insert()
        self.textview.scroller.smooth_scroll_to_mark(insert, center=True)

    def forward_search_finished(self, search_context, result):
        match_found, match_start, match_end, has_wrapped = search_context.forward_finish(result)

        if match_found:
            self.select_search_occurrence(match_start, match_end)
            self.notify("can_replace")

    @Gtk.Template.Callback()
    def forward_search(self, _widget, _data=None):
        if self.textbuffer.get_has_selection():
            _, start_at = self.textbuffer.get_selection_bounds()
        else:
            start_at = self.textbuffer.get_iter_at_mark(self.textbuffer.get_insert())

        self.search_context.forward_async(start_at, None, self.forward_search_finished)

    def backward_search_finished(self, search_context, result):
        match_found, match_start, match_end, has_wrapped = search_context.backward_finish(result)

        if match_found:
            self.select_search_occurrence(match_start, match_end)
            self.notify("can_replace")

    @Gtk.Template.Callback()
    def backward_search(self, _widget, _data=None):
        if self.textbuffer.get_has_selection():
            start_at, _ = self.textbuffer.get_selection_bounds()
        else:
            start_at = self.textbuffer.get_iter_at_mark(self.textbuffer.get_insert())

        self.search_context.backward_async(start_at, None, self.backward_search_finished)

    @Gtk.Template.Callback()
    def hide(self, *arg, **kwargs):
        self.search_mode_enabled = False

    @Gtk.Template.Callback()
    def replace_clicked(self, _widget, _data=None):
        match_start, match_end = self.textbuffer.get_selection_bounds()
        self.search_context.replace(match_start, match_end, self.replace_entry.get_text(), -1)

        iter = self.textbuffer.get_iter_at_mark(self.textbuffer.get_insert())
        self.search_context.forward_async(iter, None, self.forward_search_finished)

    @Gtk.Template.Callback()
    def replace_all(self, _widget=None, _data=None):
        self.search_context.replace_all(self.replace_entry.get_text(), -1)

    # Since the searchbar is overlayed to the textview we need to 
    # update its margin when the searchbar appears
    def update_textview_margin(self, paintable):
        self.textview.update_vertical_margin(self.paintable.get_intrinsic_height())

    def _on_notify_occurrences_count(self, *args, **kwargs):
        self.notify("can_move")
        self.notify("can_replace")
        self.notify("can_replace_all")