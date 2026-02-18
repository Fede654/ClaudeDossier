"""Session chat viewer page — async JSONL loading via thread + GLib.idle_add."""
from __future__ import annotations

import html as _html
import re
import threading

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk

from hub.data.session_parser import MessageType, SessionParser
from hub.data.session_scanner import SessionInfo

_COMPRESS_MAX_LINES = 12


def _md_to_pango(text: str, escape_newlines: bool = False) -> str:
    """Convert common markdown to Pango markup for GtkLabel.set_markup().

    Strategy: stash fenced code blocks first (so their content is never
    HTML-escaped or touched by the inline regexes), then escape the rest,
    then apply inline rules, then restore blocks.
    """
    blocks: list[str] = []

    def _stash(m: re.Match) -> str:
        code = m.group(1).rstrip('\n')
        blocks.append(f'<tt><small>{_html.escape(code)}</small></tt>')
        return f'\x00B{len(blocks) - 1}\x00'

    # 1. Extract fenced code blocks (``` ... ```)
    text = re.sub(r'```[^\n]*\n(.*?)```', _stash, text, flags=re.DOTALL)

    # 2. HTML-escape remainder so < > & don't break Pango
    text = _html.escape(text)

    # 3. Inline code — group(1) is already escaped, use as-is inside <tt>
    text = re.sub(r'`([^`\n]+)`', lambda m: f'<tt>{m.group(1)}</tt>', text)

    # 4. Bold (before italic so *** is handled as bold wrapping italic)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)

    # 5. Italic (single * not adjacent to another *)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)

    # 6. ATX headings → bold
    text = re.sub(r'^#{1,3} (.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # 7. Restore code blocks (\x00 is not touched by html.escape)
    for i, block in enumerate(blocks):
        text = text.replace(f'\x00B{i}\x00', block)

    # 8. Newline escaping — append ↵ marker before each line break
    if escape_newlines:
        text = text.replace('\n', '<span alpha="50%" size="small"> ↵</span>\n')

    return text


class SessionPage(Gtk.Box):
    __gtype_name__ = 'SessionPage'

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._current = None
        self._cancel_flag = threading.Event()
        self._build_ui()

    def _build_ui(self):
        # Metadata bar
        self._meta = Gtk.Label(xalign=0)
        self._meta.add_css_class('caption')
        self._meta.set_margin_start(12)
        self._meta.set_margin_top(8)
        self._meta.set_margin_bottom(4)
        self.append(self._meta)
        self.append(Gtk.Separator())

        # Settings bar — gear button opens popover with view options
        tbar = Gtk.Box(spacing=6)
        tbar.set_margin_start(12)
        tbar.set_margin_end(8)
        tbar.set_margin_top(2)
        tbar.set_margin_bottom(2)

        # Build settings popover with boxed-list
        popover = Gtk.Popover()
        listbox = Gtk.ListBox()
        listbox.add_css_class('boxed-list')
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.set_margin_top(8)
        listbox.set_margin_bottom(8)
        listbox.set_margin_start(8)
        listbox.set_margin_end(8)

        self._progress_row = Adw.SwitchRow(title='Show progress events')
        self._escape_nl_row = Adw.SwitchRow(
            title='Escape newlines',
            subtitle='Mark line endings with ↵',
        )
        self._compress_row = Adw.SwitchRow(
            title='Compress large blocks',
            subtitle=f'Collapse messages over {_COMPRESS_MAX_LINES} lines',
        )
        self._compress_row.set_active(True)  # on by default

        for srow in (self._progress_row, self._escape_nl_row, self._compress_row):
            listbox.append(srow)
            srow.connect('notify::active', lambda *_: self._reload())

        popover.set_child(listbox)

        spacer = Gtk.Label(hexpand=True)
        tbar.append(spacer)

        settings_btn = Gtk.MenuButton()
        settings_btn.set_icon_name('preferences-system-symbolic')
        settings_btn.add_css_class('flat')
        settings_btn.set_tooltip_text('View options')
        settings_btn.set_popover(popover)
        tbar.append(settings_btn)

        self.append(tbar)

        # Chat area
        self._scroll_window = Gtk.ScrolledWindow()
        self._scroll_window.set_vexpand(True)
        self._chat = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._chat.set_margin_start(12)
        self._chat.set_margin_end(12)
        self._chat.set_margin_top(8)
        self._chat.set_margin_bottom(8)
        self._scroll_window.set_child(self._chat)
        self.append(self._scroll_window)

        # Action bar
        ab = Gtk.ActionBar()
        self._copy_btn = Gtk.Button(label='Copy Resume Command')
        self._copy_btn.add_css_class('suggested-action')
        self._copy_btn.connect('clicked', self._copy_resume)
        ab.pack_start(self._copy_btn)

        self._export_btn = Gtk.Button(label='Export MD')
        self._export_btn.connect('clicked', self._export)
        ab.pack_end(self._export_btn)

        self._delete_btn = Gtk.Button(label='Delete')
        self._delete_btn.add_css_class('destructive-action')
        self._delete_btn.connect('clicked', self._delete)
        ab.pack_end(self._delete_btn)

        self.append(ab)

    def load(self, session: SessionInfo) -> None:
        self._cancel_flag.set()
        self._cancel_flag = threading.Event()
        self._current = session

        self._meta.set_text(
            f"ID: {session.session_id[:8]}…  ·  Branch: {session.git_branch}  ·  "
            f"Messages: {session.message_count}  ·  {session.modified.strftime('%Y-%m-%d %H:%M')}"
        )
        self._clear_chat()
        spinner = Gtk.Spinner()
        spinner.start()
        self._chat.append(spinner)

        # Capture settings on the main thread before spawning worker
        cancel = self._cancel_flag
        include_progress = self._progress_row.get_active()
        escape_nl = self._escape_nl_row.get_active()
        compress = self._compress_row.get_active()

        def _parse():
            parser = SessionParser(include_progress=include_progress)
            messages = parser.parse(session.jsonl_path)
            if not cancel.is_set():
                GLib.idle_add(self._render, messages, cancel, escape_nl, compress)

        threading.Thread(target=_parse, daemon=True).start()

    def _reload(self):
        if self._current:
            self.load(self._current)

    def _render(self, messages, cancel, escape_nl=False, compress=True):
        if cancel.is_set():
            return GLib.SOURCE_REMOVE
        self._clear_chat()
        for msg in messages:
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            row.set_margin_bottom(4)
            role = Gtk.Label(xalign=0)
            role.add_css_class('caption')
            body = Gtk.Label(xalign=0, wrap=True, selectable=True)
            body.set_hexpand(True)
            body.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)

            if msg.type == MessageType.USER:
                role.set_text('You')
                row.add_css_class('user-msg')
            elif msg.type == MessageType.ASSISTANT:
                role.set_text('Claude')
                row.add_css_class('assistant-msg')
            else:
                role.set_text('System')

            lines = msg.text.split('\n')
            compressed = compress and len(lines) > _COMPRESS_MAX_LINES
            display_text = '\n'.join(lines[:_COMPRESS_MAX_LINES]) if compressed else msg.text

            try:
                body.set_markup(_md_to_pango(display_text, escape_nl))
            except Exception:
                body.set_text(display_text)

            row.append(role)
            row.append(body)

            if compressed:
                remaining = len(lines) - _COMPRESS_MAX_LINES
                expand_btn = Gtk.Button(label=f'▼  Show {remaining} more lines')
                expand_btn.add_css_class('flat')
                expand_btn.set_halign(Gtk.Align.START)

                def _expand(btn, _body=body, _text=msg.text, _escape=escape_nl, _row=row):
                    try:
                        _body.set_markup(_md_to_pango(_text, _escape))
                    except Exception:
                        _body.set_text(_text)
                    _row.remove(btn)

                expand_btn.connect('clicked', _expand)
                row.append(expand_btn)

            self._chat.append(row)

        GLib.idle_add(self._scroll_to_bottom)
        return GLib.SOURCE_REMOVE

    def _scroll_to_bottom(self):
        adj = self._scroll_window.get_vadjustment()
        adj.set_value(adj.get_upper() - adj.get_page_size())
        return GLib.SOURCE_REMOVE

    def _clear_chat(self):
        child = self._chat.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._chat.remove(child)
            child = next_child

    def _copy_resume(self, _):
        if not self._current:
            return
        cmd = f"claude --resume {self._current.session_id}"
        self.get_clipboard().set(cmd)
        self._toast(f'Copied: {cmd}')

    def _delete(self, _):
        if not self._current:
            return
        dialog = Adw.AlertDialog.new(
            'Delete Session?',
            'The session file will be moved to Trash. You can undo this.'
        )
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('trash', 'Move to Trash')
        dialog.set_response_appearance('trash', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect('response', self._on_delete_response)
        dialog.present(self.get_root())

    def _on_delete_response(self, dialog, response):
        if response != 'trash':
            return
        from gi.repository import Gio
        f = Gio.File.new_for_path(str(self._current.jsonl_path))
        try:
            f.trash(None)
            self._toast('Session moved to Trash')
        except Exception as e:
            self._toast(f'Error: {e}')

    def _export(self, _):
        if not self._current:
            return
        parser = SessionParser()
        msgs = parser.parse(self._current.jsonl_path)
        lines = [f"# Session {self._current.session_id}\n\n"]
        for m in msgs:
            role = "**You**" if m.type == MessageType.USER else "**Claude**"
            lines.append(f"{role}\n\n{m.text}\n\n---\n\n")
        md = "".join(lines)
        chooser = Gtk.FileDialog()
        chooser.set_initial_name(f"session-{self._current.session_id[:8]}.md")
        chooser.save(self.get_root(), None, self._on_export_saved, md)

    def _on_export_saved(self, dialog, result, md):
        try:
            from gi.repository import Gio
            f = dialog.save_finish(result)
            f.replace_contents(
                md.encode(), None, False,
                Gio.FileCreateFlags.REPLACE_DESTINATION, None
            )
        except Exception:
            pass

    def _toast(self, msg: str):
        win = self.get_root()
        if hasattr(win, 'add_toast'):
            win.add_toast(Adw.Toast.new(msg))
