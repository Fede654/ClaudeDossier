"""Reusable memory list + edit dialog widget."""
from __future__ import annotations

from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk, GObject

from hub.data.memory_reader import (
    read_memory_dir, write_memory, create_memory, delete_memory,
    MemoryEntry, MtimeConflictError,
)


class MemoryEditor(Adw.PreferencesGroup):
    __gtype_name__ = 'MemoryEditor'

    __gsignals__ = {
        'memory-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, memory_dir: Path):
        super().__init__(title="Memory")
        self._memory_dir = Path(memory_dir)
        self._entries: list[MemoryEntry] = []
        self._rows: list[Adw.ActionRow] = []
        self.refresh()

    def refresh(self):
        """Reload memory files and rebuild the row list."""
        # Remove all previously tracked rows
        for row in self._rows:
            try:
                self.remove(row)
            except Exception:
                pass
        self._rows = []

        self._entries = read_memory_dir(self._memory_dir)

        if not self._entries:
            empty = Adw.ActionRow(
                title="No memories yet",
                subtitle="Memory files will appear here",
            )
            self._rows.append(empty)
            self.add(empty)
        else:
            for entry in self._entries:
                row = self._make_row(entry)
                self._rows.append(row)
                self.add(row)

        # "New Memory" button row always at the bottom
        new_row = Adw.ActionRow(title="New Memory...")
        new_row.set_activatable(True)
        new_row.add_prefix(Gtk.Image.new_from_icon_name("list-add-symbolic"))
        new_row.connect("activated", self._on_new_memory)
        self._rows.append(new_row)
        self.add(new_row)

    def _make_row(self, entry: MemoryEntry) -> Adw.ActionRow:
        type_badge = {"user": "[user]", "feedback": "[feedback]",
                      "project": "[project]", "reference": "[ref]"}
        badge = type_badge.get(entry.type, f"[{entry.type}]")
        row = Adw.ActionRow(
            title=f"{entry.name}  {badge}",
            subtitle=entry.description or "",
        )
        row.set_activatable(True)
        row.connect("activated", lambda _, e=entry: self._on_edit(e))

        delete_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        delete_btn.set_valign(Gtk.Align.CENTER)
        delete_btn.add_css_class("flat")
        delete_btn.connect("clicked", lambda _, e=entry: self._on_delete(e))
        row.add_suffix(delete_btn)
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))

        return row

    # ------------------------------------------------------------------ dialogs

    def _on_edit(self, entry: MemoryEntry):
        """Open edit dialog for a memory entry."""
        dialog = Adw.Dialog()
        dialog.set_title(f"Edit: {entry.name}")
        dialog.set_content_width(600)
        dialog.set_content_height(500)

        toolbar_view = Adw.ToolbarView()

        hbar = Adw.HeaderBar()
        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        hbar.pack_end(save_btn)
        toolbar_view.add_top_bar(hbar)

        tv = Gtk.TextView()
        tv.set_monospace(True)
        tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        tv.set_top_margin(12)
        tv.set_bottom_margin(12)
        tv.set_left_margin(12)
        tv.set_right_margin(12)
        tv.get_buffer().set_text(entry.content)

        sw = Gtk.ScrolledWindow(vexpand=True)
        sw.set_child(tv)
        toolbar_view.set_content(sw)

        dialog.set_child(toolbar_view)

        def on_save(_btn):
            buf = tv.get_buffer()
            entry.content = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
            try:
                write_memory(entry, expected_mtime=entry.mtime)
                self._toast("Saved")
                dialog.close()
                self.refresh()
                self.emit("memory-changed")
            except MtimeConflictError:
                self._toast("File changed externally — reload and retry")

        save_btn.connect("clicked", on_save)
        dialog.present(self.get_root())

    def _on_new_memory(self, _row):
        """Dialog to create a new memory."""
        dialog = Adw.Dialog()
        dialog.set_title("New Memory")
        dialog.set_content_width(420)
        dialog.set_content_height(380)

        toolbar_view = Adw.ToolbarView()

        hbar = Adw.HeaderBar()
        create_btn = Gtk.Button(label="Create")
        create_btn.add_css_class("suggested-action")
        hbar.pack_end(create_btn)
        toolbar_view.add_top_bar(hbar)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)

        group = Adw.PreferencesGroup()
        group.set_margin_top(12)
        group.set_margin_bottom(12)
        group.set_margin_start(12)
        group.set_margin_end(12)

        name_row = Adw.EntryRow(title="Name")
        desc_row = Adw.EntryRow(title="Description")

        type_row = Adw.ComboRow(title="Type")
        types = Gtk.StringList.new(["project", "user", "feedback", "reference"])
        type_row.set_model(types)

        group.add(name_row)
        group.add(desc_row)
        group.add(type_row)

        clamp.set_child(group)
        scroll.set_child(clamp)
        toolbar_view.set_content(scroll)
        dialog.set_child(toolbar_view)

        def on_create(_btn):
            name = name_row.get_text().strip()
            desc = desc_row.get_text().strip()
            idx = type_row.get_selected()
            mtype = types.get_string(idx)
            if not name:
                return
            self._memory_dir.mkdir(parents=True, exist_ok=True)
            create_memory(
                self._memory_dir,
                name=name,
                type=mtype,
                description=desc,
                content="",
            )
            self._toast(f"Created: {name}")
            dialog.close()
            self.refresh()
            self.emit("memory-changed")

        create_btn.connect("clicked", on_create)
        dialog.present(self.get_root())

    def _on_delete(self, entry: MemoryEntry):
        """Confirm and delete a memory."""
        confirm = Adw.AlertDialog()
        confirm.set_heading(f"Delete \u2018{entry.name}\u2019?")
        confirm.set_body(
            "The file will be removed. Claude Code may recreate related notes "
            "in future sessions."
        )
        confirm.add_response("cancel", "Cancel")
        confirm.add_response("delete", "Delete")
        confirm.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        confirm.set_default_response("cancel")

        def on_response(_dlg, response):
            if response == "delete":
                delete_memory(entry)
                self._toast(f"Deleted: {entry.name}")
                self.refresh()
                self.emit("memory-changed")

        confirm.connect("response", on_response)
        confirm.present(self.get_root())

    # --------------------------------------------------------------------- util

    def _toast(self, msg: str) -> None:
        win = self.get_root()
        if hasattr(win, "add_toast"):
            toast = Adw.Toast.new(msg)
            toast.set_timeout(2)
            win.add_toast(toast)
