"""Session chat viewer page — async JSONL loading via thread + GLib.idle_add."""
from __future__ import annotations

import html as _html
import re
import threading

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, GObject, Gtk, Pango

from hub.data.session_parser import MessageType, SessionParser
from hub.data.session_scanner import SessionInfo

_COMPRESS_MAX_LINES = 12
_TRUNCATE_LINE_WIDTH = 120
_ITALIC_RE = re.compile(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)')
_BOLD_SPLIT_RE = re.compile(r'(<b>.*?</b>)')


def _wrap_long_lines(text: str) -> str:
    """Fold lines exceeding _TRUNCATE_LINE_WIDTH chars into multiple lines."""
    out = []
    for line in text.split('\n'):
        while len(line) > _TRUNCATE_LINE_WIDTH:
            out.append(line[:_TRUNCATE_LINE_WIDTH])
            line = line[_TRUNCATE_LINE_WIDTH:]
        out.append(line)
    return '\n'.join(out)


def _md_to_pango(text: str) -> str:
    """Convert common markdown to Pango markup for GtkLabel.set_markup().

    Strategy:
      1. Stash fenced code blocks (``` ... ```) — never escaped or inline-processed.
      2. HTML-escape the remainder.
      3. Stash inline code spans (`...`) — must be stashed BEFORE bold/italic so
         that * characters inside backtick spans don't trigger the italic regex.
      4. Apply bold / italic / heading rules.
      5. Restore all stashed spans in reverse stash order.
    """
    stash: list[str] = []

    def _stash_block(m: re.Match) -> str:
        code = m.group(1).rstrip('\n')
        stash.append(f'<tt><small>{_html.escape(code)}</small></tt>')
        return f'\x00S{len(stash) - 1}\x00'

    def _stash_inline(m: re.Match) -> str:
        # m.group(1) is already HTML-escaped at this point
        stash.append(f'<tt>{m.group(1)}</tt>')
        return f'\x00S{len(stash) - 1}\x00'

    # 1. Extract fenced code blocks (``` ... ```)
    text = re.sub(r'```[^\n]*\n(.*?)```', _stash_block, text, flags=re.DOTALL)

    # 2. HTML-escape remainder so < > & don't break Pango
    text = _html.escape(text)

    # 3. Stash inline code spans BEFORE applying bold/italic to avoid
    #    the italic regex matching * characters inside <tt> spans.
    text = re.sub(r'`([^`\n]+)`', _stash_inline, text)

    # 4a. Bold (before italic so *** is handled as bold wrapping italic)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)

    # 4b. Italic — run separately on each segment so italic spans cannot cross
    #     <b>...</b> boundaries (which would produce invalid Pango nesting).
    def _apply_italic(seg: str) -> str:
        return _ITALIC_RE.sub(r'<i>\1</i>', seg)

    # Split into alternating [outside, <b>inside</b>, outside, ...] parts
    parts = _BOLD_SPLIT_RE.split(text)
    text = ''.join(
        # For bold spans: apply italic to the inner content only
        f'<b>{_apply_italic(p[3:-4])}</b>' if p.startswith('<b>') and p.endswith('</b>')
        else _apply_italic(p)
        for p in parts
    )

    # 4c. ATX headings → bold
    text = re.sub(r'^#{1,3} (.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # 5. Restore all stashed spans (\x00 bytes are untouched by html.escape)
    for i, span in enumerate(stash):
        text = text.replace(f'\x00S{i}\x00', span)

    return text


def _set_markup(label: Gtk.Label, raw: str) -> None:
    """Render raw text as Pango markup on label, falling back to plain text.

    GtkLabel.set_markup() prints a GLib warning (not a Python exception) when
    markup is malformed.  We validate first with Pango.parse_markup so that
    invalid markup silently degrades to plain text instead of spamming stderr.
    """
    markup = _md_to_pango(raw)
    try:
        ok, _, _, _ = Pango.parse_markup(markup, -1, '\x00')
    except Exception:
        ok = False
    if ok:
        label.set_markup(markup)
    else:
        label.set_text(raw)


class SessionPage(Gtk.Box):
    __gtype_name__ = 'SessionPage'
    __gsignals__ = {
        'session-deleted': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._current = None
        self._cancel_flag = threading.Event()
        self._scroll_positions: dict[str, float] = {}
        self._build_ui()

    def _build_ui(self):
        # Single combined header: session-id button + metadata label + settings button
        tbar = Gtk.Box(spacing=6)
        tbar.set_margin_start(12)
        tbar.set_margin_end(8)
        tbar.set_margin_top(4)
        tbar.set_margin_bottom(4)

        # Clickable session-ID chip — copies full ID to clipboard
        self._sid_btn = Gtk.Button()
        self._sid_btn.add_css_class('flat')
        self._sid_btn.add_css_class('caption')
        self._sid_btn.set_tooltip_text('Click to copy session ID')
        self._sid_btn.connect('clicked', self._copy_session_id)
        self._sid_label = Gtk.Label()
        self._sid_label.add_css_class('caption')
        self._sid_btn.set_child(self._sid_label)
        tbar.append(self._sid_btn)

        self._meta = Gtk.Label(xalign=0)
        self._meta.add_css_class('caption')
        self._meta.set_hexpand(True)
        self._meta.set_ellipsize(Pango.EllipsizeMode.END)
        tbar.append(self._meta)

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
            title='Wrap long lines',
            subtitle=f'Fold lines exceeding {_TRUNCATE_LINE_WIDTH} characters',
        )
        self._escape_nl_row.set_active(True)  # on by default
        self._compress_row = Adw.SwitchRow(
            title='Compress large blocks',
            subtitle=f'Collapse messages over {_COMPRESS_MAX_LINES} lines',
        )
        self._compress_row.set_active(True)  # on by default

        self._scroll_bottom_row = Adw.SwitchRow(title='Scroll to bottom on open')

        for srow in (self._progress_row, self._escape_nl_row, self._compress_row, self._scroll_bottom_row):
            listbox.append(srow)
            srow.connect('notify::active', lambda *_: self._reload())

        popover.set_child(listbox)

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
        self._chat = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._chat.set_margin_start(16)
        self._chat.set_margin_end(16)
        self._chat.set_margin_top(12)
        self._chat.set_margin_bottom(12)
        self._scroll_window.set_child(self._chat)
        self.append(self._scroll_window)

        # Action bar
        ab = Gtk.ActionBar()
        self._delete_btn = Gtk.Button(label='Delete')
        self._delete_btn.add_css_class('destructive-action')
        self._delete_btn.connect('clicked', self._delete)
        ab.pack_start(self._delete_btn)

        self._copy_btn = Gtk.Button(label='Resume Conversation')
        self._copy_btn.add_css_class('suggested-action')
        self._copy_btn.connect('clicked', self._copy_resume)
        ab.pack_end(self._copy_btn)

        self._export_btn = Gtk.Button(label='Export MD')
        self._export_btn.connect('clicked', self._export)
        ab.pack_end(self._export_btn)

        self.append(ab)

    def load(self, session: SessionInfo) -> None:
        # Persist scroll position of the session we're leaving
        if self._current is not None:
            adj = self._scroll_window.get_vadjustment()
            self._scroll_positions[self._current.session_id] = adj.get_value()

        self._cancel_flag.set()
        self._cancel_flag = threading.Event()
        self._current = session

        branch = _html.escape(session.git_branch or '—')
        date = session.modified.strftime('%Y-%m-%d %H:%M')
        self._sid_label.set_markup(
            f'<span weight="bold">{_html.escape(session.session_id[:8])}…</span>'
        )
        self._meta.set_markup(
            f'<span alpha="50%">·  </span>'
            f'<span>⎇  {branch}</span>'
            f'<span alpha="50%">  ·  </span>'
            f'<span>{session.message_count} msgs</span>'
            f'<span alpha="50%">  ·  </span>'
            f'<span alpha="70%">{date}</span>'
        )
        self._clear_chat()
        spinner = Gtk.Spinner()
        spinner.start()
        self._chat.append(spinner)

        # Capture settings on the main thread before spawning worker
        cancel = self._cancel_flag
        include_progress = self._progress_row.get_active()
        truncate = self._escape_nl_row.get_active()
        compress = self._compress_row.get_active()
        scroll_bottom = self._scroll_bottom_row.get_active()
        saved_scroll = self._scroll_positions.get(session.session_id)

        def _parse():
            parser = SessionParser(include_progress=include_progress)
            messages = parser.parse(session.jsonl_path)
            if not cancel.is_set():
                GLib.idle_add(self._render, messages, cancel, truncate, compress, scroll_bottom, saved_scroll)

        threading.Thread(target=_parse, daemon=True).start()

    def _reload(self):
        if self._current:
            self.load(self._current)

    def _render(self, messages, cancel, truncate=False, compress=True, scroll_bottom=False, saved_scroll=None):
        if cancel.is_set():
            return GLib.SOURCE_REMOVE
        self._clear_chat()
        for msg in messages:
            # Outer row: horizontal, holds spacer + bubble (user) or bubble alone (others)
            outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            outer.set_margin_bottom(4)

            # Bubble: vertical box with role label + body
            bubble = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

            role = Gtk.Label(xalign=0)
            role.add_css_class('caption')

            body = Gtk.Label(xalign=0, wrap=True, selectable=True)
            body.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)

            if msg.type == MessageType.USER:
                role.set_text('You')
                role.set_xalign(1.0)
                role.add_css_class('msg-role-you')
                bubble.add_css_class('user-msg')
                # Push bubble to the right with a flexible spacer
                spacer = Gtk.Box()
                spacer.set_hexpand(True)
                outer.append(spacer)
                outer.append(bubble)
                # Constrain width so bubble doesn't stretch full-width
                body.set_max_width_chars(70)
                body.set_hexpand(False)
            elif msg.type == MessageType.ASSISTANT:
                role.set_text('Claude')
                role.add_css_class('msg-role-claude')
                bubble.add_css_class('assistant-msg')
                outer.append(bubble)
                bubble.set_hexpand(True)
                body.set_hexpand(True)
            else:
                role.set_text('System')
                role.add_css_class('dim-label')
                outer.append(bubble)
                bubble.set_hexpand(True)
                body.set_hexpand(True)

            lines = msg.text.split('\n')
            compressed = compress and len(lines) > _COMPRESS_MAX_LINES
            raw = '\n'.join(lines[:_COMPRESS_MAX_LINES]) if compressed else msg.text
            display_text = _wrap_long_lines(raw) if truncate else raw

            _set_markup(body, display_text)

            bubble.append(role)
            bubble.append(body)

            if compressed:
                remaining = len(lines) - _COMPRESS_MAX_LINES
                expand_btn = Gtk.Button(label=f'▼  Show {remaining} more lines')
                expand_btn.add_css_class('flat')
                expand_btn.set_halign(Gtk.Align.START)

                def _expand(btn, _body=body, _full=msg.text, _trunc=truncate, _bubble=bubble):
                    full = _wrap_long_lines(_full) if _trunc else _full
                    _set_markup(_body, full)
                    _bubble.remove(btn)

                expand_btn.connect('clicked', _expand)
                bubble.append(expand_btn)

            self._chat.append(outer)

        if saved_scroll is not None:
            GLib.idle_add(lambda v=saved_scroll: self._restore_scroll(v), priority=GLib.PRIORITY_LOW)
        elif scroll_bottom:
            GLib.idle_add(self._scroll_to_bottom, priority=GLib.PRIORITY_LOW)
        return GLib.SOURCE_REMOVE

    def _restore_scroll(self, value, _retries=5):
        adj = self._scroll_window.get_vadjustment()
        upper = adj.get_upper()
        page = adj.get_page_size()
        if upper > page:
            adj.set_value(min(value, upper - page))
        elif _retries > 0:
            GLib.timeout_add(80, lambda v=value, r=_retries - 1: self._restore_scroll(v, r))
        return GLib.SOURCE_REMOVE

    def _scroll_to_bottom(self, _retries=5):
        adj = self._scroll_window.get_vadjustment()
        upper = adj.get_upper()
        page = adj.get_page_size()
        if upper > page:
            adj.set_value(upper - page)
        elif _retries > 0:
            GLib.timeout_add(80, lambda r=_retries - 1: self._scroll_to_bottom(r))
        return GLib.SOURCE_REMOVE

    def _clear_chat(self):
        child = self._chat.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._chat.remove(child)
            child = next_child

    def _copy_session_id(self, _):
        if not self._current:
            return
        sid = self._current.session_id
        try:
            from gi.repository import Gdk, GObject as GO
            provider = Gdk.ContentProvider.new_for_value(GO.Value(str, sid))
            self.get_display().get_clipboard().set_content(provider)
        except Exception:
            import subprocess
            for args in (['wl-copy'], ['xclip', '-selection', 'clipboard']):
                try:
                    subprocess.run(args, input=sid.encode(), check=True, capture_output=True)
                    break
                except (FileNotFoundError, subprocess.CalledProcessError):
                    continue
        self._toast(f'Copied: {sid[:8]}…')

    def _copy_resume(self, _):
        if not self._current:
            return
        import shlex
        project_dir = shlex.quote(self._current.project_path)
        sid = self._current.session_id
        cmd = f"cd {project_dir} && claude --resume {sid}"
        import subprocess

        # Try to launch in a terminal directly
        terminals = [
            ['gnome-terminal', '--', 'bash', '-c', f'{cmd}; exec bash'],
            ['kitty', '--', 'bash', '-c', f'{cmd}; exec bash'],
            ['alacritty', '-e', 'bash', '-c', f'{cmd}; exec bash'],
            ['xterm', '-e', 'bash', '-c', f'{cmd}; exec bash'],
        ]
        for args in terminals:
            try:
                subprocess.Popen(args)
                self._toast(f'Resuming session in terminal…')
                return
            except FileNotFoundError:
                continue

        # No terminal found — fall back to copying the command
        try:
            from gi.repository import Gdk, GObject
            provider = Gdk.ContentProvider.new_for_value(GObject.Value(str, cmd))
            self.get_display().get_clipboard().set_content(provider)
        except Exception:
            for args in (['wl-copy'], ['xclip', '-selection', 'clipboard']):
                try:
                    subprocess.run(args, input=cmd.encode(), check=True, capture_output=True)
                    break
                except (FileNotFoundError, subprocess.CalledProcessError):
                    continue
        plain_cmd = f"claude --resume {sid}"
        self._toast(f'No terminal found — copied: {plain_cmd}')

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
            self.emit('session-deleted')
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
        except Exception as e:
            self._toast(f'Export failed: {e}')

    def _toast(self, msg: str):
        win = self.get_root()
        if hasattr(win, 'add_toast'):
            win.add_toast(Adw.Toast.new(msg))
