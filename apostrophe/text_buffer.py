import logging
from contextlib import contextmanager
from itertools import cycle

import gi
import regex as re

gi.require_version('Gtk', '4.0')
gi.require_version('GtkSource', '5')

from gi.repository import Gio, GLib, GObject, Gtk, GtkSource

from apostrophe.helpers import user_action
from apostrophe.markup_regex import CHECKLIST, LIST, ORDERED_LIST
from apostrophe.settings import Settings

LOGGER = logging.getLogger('apostrophe')

class ApostropheTextBuffer(GtkSource.Buffer):
    __gtype_name__ = "ApostropheTextBuffer"

    __gsignals__ = {
        'attempted-hemingway': (GObject.SignalFlags.ACTION, None, ()),
        'changed-debounced': (GObject.SIGNAL_RUN_LAST, None, ()),
    }

    hemingway_mode = GObject.Property(type=bool, default=False)
    paste_ongoing = GObject.Property(type=bool, default=False)
    changed_debounced_timeout = GObject.Property(type=int, default=100)
    changed_debounced_timeout_id = None

    def __init__(self):
        super().__init__()

        self.settings = Settings.new()

        self.settings.bind("hemingway-mode", self, "hemingway-mode",
                           Gio.SettingsBindFlags.DEFAULT | Gio.SettingsBindFlags.GET_NO_CHANGES)

        self.connect("paste-done", self._on_clipboard_paste_finished)

    @contextmanager
    def _temp_disable_hemingway(self):
        ''' Disables hemingway mode before an action and enables it right away
        '''
        hemingway_cache = self.hemingway_mode
        if hemingway_cache:
            self.hemingway_mode = False
        yield self
        self.hemingway_mode = hemingway_cache

    def get_current_sentence_bounds(self):
        cursor_iter = self.get_iter_at_mark(self.get_insert())
        start_sentence = cursor_iter.copy()
        if not start_sentence.starts_sentence():
            start_sentence.backward_sentence_start()
        end_sentence = cursor_iter.copy()
        if not end_sentence.ends_sentence():
            end_sentence.forward_sentence_end()

        return (start_sentence, end_sentence)

    def get_line_bounds(self, iter):
        # backward_line() doesn't seem to work as expected
        # so we just find the end of the line and backward the number of characters
        # that line has
        end_line = iter.copy()
        if not end_line.ends_line():
            end_line.forward_to_line_end()
        start_line = end_line.copy()
        start_line.backward_chars(end_line.get_line_offset())

        return (start_line, end_line)

    def get_current_line_bounds(self):
        return self.get_line_bounds(self.get_iter_at_mark(self.get_insert()))
    
    def get_previous_line_bounds(self):
        iter = self.get_iter_at_mark(self.get_insert()).copy()
        iter.backward_chars(1)
        return self.get_line_bounds(iter)

    def _indent(self):
        '''Takes over tab insertions.
           If the insertion happens within a list, 
           it nicely handles it, otherwise inserts a plain \t'''
        with user_action(self):
            start_line, end_line = self.get_current_line_bounds()
            current_sentence = self.get_text(start_line, end_line, True)
            text = ""

            # Indent unordered lists
            match = re.fullmatch(LIST, current_sentence)
            if match and not match.group("text"):
                symbols = cycle(['-', '*', '+'])
                for i in range(3):
                    if next(symbols) == match.group("symbol"):
                        break
                next_symbol = next(symbols)
                indent = "\t" if "\t" in match.group("indent") else "    " + match.group("indent")

                with self._temp_disable_hemingway():
                    self.delete(start_line, end_line)
                text = indent + next_symbol + " "

            # Indent ordered lists
            match = re.fullmatch(ORDERED_LIST, current_sentence)
            if match and not match.group("text"):
                indent = "\t" if "\t" in match.group("indent") else "    " + match.group("indent")

                with self._temp_disable_hemingway():
                    self.delete(start_line, end_line)
                text = indent + "1" + match.group("delimiter") + " "

            position = self.get_iter_at_mark(self.get_insert())
            GtkSource.Buffer.do_insert_text(self, position, text, -1)

    def _unindent(self, *args):
        with user_action(self):
            if self.hemingway_mode:
                self.emit("attempted-hemingway")
                return

            start_line, end_line = self.get_current_line_bounds()
            current_sentence = self.get_text(start_line, end_line, True)

            # Unindent unordered lists
            match = re.fullmatch(LIST, current_sentence)
            if match:
                indent = match.group("indent")

                if indent == "":
                    # nothing to unindent
                    return

                # iterate over previous lines and match the symbol and indentation
                # of the first occurence we find that had a smaller indentation
                # than the current one
                tmp_start = start_line.copy()
                for _ in range(50):
                    tmp_start.backward_char()
                    tmp_start, tmp_end = self.get_line_bounds(tmp_start)
                    if tmp_match := re.fullmatch(LIST, self.get_text(tmp_start, tmp_end, True)):
                        indent = tmp_match.group("indent")
                        next_symbol = tmp_match.group("symbol")
                    else:
                        break
                    if len(indent) < len(match.group("indent")):
                        break

                self.delete(start_line, end_line)
                text = indent + next_symbol + " "
                if match.group("text"):
                    text += match.group("text")

                position = self.get_iter_at_mark(self.get_insert())
                GtkSource.Buffer.do_insert_text(self, position, text, -1)

            # Unindent regular tabs
            else:
                pen_iter = self.get_end_iter()
                pen_iter.backward_char()
                end_iter = self.get_end_iter()

                if pen_iter.get_char() == "\t":
                    self.delete(pen_iter, end_iter)

    def _autocomplete_lists(self):
        with user_action(self):
            start_line, end_line = self.get_previous_line_bounds()
            previous_sentence = self.get_text(start_line, end_line, True)

            # Get current cursor position
            cursor_mark = self.get_insert()
            cursor_iter = self.get_iter_at_mark(cursor_mark)

            text_to_insert = ""
            delete_current_line = False

            # ORDERED LISTS
            match = re.match(ORDERED_LIST, previous_sentence)
            if match:
                if match.group("text"):
                    if match.group("number"):
                        next_prefix = (match.group("indent") +
                                       str(int(match.group("number")) + 1) +
                                       match.group("delimiter") + " ")
                        text_to_insert = next_prefix
                else:
                    delete_current_line = True

            # CHECKLIST
            elif match:= re.match(CHECKLIST, previous_sentence):
                if match.group("text"):
                    next_prefix = match.group(
                        "indent") + match.group("symbol") + " [ ] "
                    text_to_insert = next_prefix
                else:
                    delete_current_line = True

            # UNORDERED LISTS
            elif match:= re.match(LIST, previous_sentence):
                if match.group("text"):
                    next_prefix = match.group(
                        "indent") + match.group("symbol") + " "
                    text_to_insert = next_prefix
                else:
                    delete_current_line = True

            # Apply changes
            if delete_current_line:
                with self._temp_disable_hemingway():
                    self.delete(start_line, end_line)
            elif text_to_insert:
                self.insert(cursor_iter, text_to_insert)

    def do_insert_text(self, position, text, length):
        if self.hemingway_mode and self.get_has_selection():
            return False

        move_cursor = None
        modified_text = text

        if not self.paste_ongoing:
            if text == "\n":
                GtkSource.Buffer.do_insert_text(self, position, text, length)
                GLib.idle_add(self._autocomplete_lists)
                return

            elif text == "\t":
                GtkSource.Buffer.do_insert_text(self, position, text, length)
                GLib.idle_add(self._indent)
                return

            elif text in "([{\"<":
                pairs = {
                    "(": ")",
                    "[": "]",
                    "{": "}",
                    '"': '"',
                    "<": ">"
                }

                # is the next character whitespace?
                next_iter = position.copy()
                if (next_iter.get_char().isspace() or next_iter.is_end()):
                    modified_text = text + pairs[text]
                    move_cursor = -1

            elif text in ")]}\">":
                # check if the character at cursor matches what we're typing
                if position.get_char() == text:
                    # skip insertion, just move cursor
                    cursor_iter = self.get_iter_at_mark(self.get_insert())
                    cursor_iter.forward_cursor_positions(1)
                    self.place_cursor(cursor_iter)
                    return  # don't insert anything

        GtkSource.Buffer.do_insert_text(self, position, modified_text, -1)

        # Handle cursor movement after insertion
        if move_cursor:
            GLib.idle_add(lambda: self._move_cursor_relative(move_cursor))

    def _move_cursor_relative(self, offset):
        try:
            cursor_iter = self.get_iter_at_mark(self.get_insert())
            if offset > 0:
                cursor_iter.forward_cursor_positions(offset)
            else:
                cursor_iter.backward_cursor_positions(abs(offset))
            self.place_cursor(cursor_iter)
        except Exception as e:
            LOGGER.warning(f"Cursor positioning error: {e}")
            pass

    def do_delete_range(self, start, end):
        if self.hemingway_mode:
            self.emit("attempted-hemingway")
        else:
            GtkSource.Buffer.do_delete_range(self, start, end)

    def changed_debounced(self):
        self.emit("changed-debounced")
        self.changed_debounced_timeout_id = None

    def do_changed(self):
        if self.changed_debounced_timeout_id:
            GLib.source_remove(self.changed_debounced_timeout_id)
            self.changed_debounced_timeout_id = None
        self.changed_debounced_timeout_id = GLib.timeout_add(self.changed_debounced_timeout, self.changed_debounced)

    def _on_clipboard_paste_finished(self, *args, **kwargs):
        self.paste_ongoing = False
