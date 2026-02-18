"""Claude Session Hub — GTK4/Adwaita application."""
import logging

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gettext import gettext as _

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from hub.main_window import MainWindow

LOGGER = logging.getLogger('hub')


class Application(Adw.Application):

    def __init__(self, application_id, *args, **kwargs):
        super().__init__(*args, application_id=application_id,
                         flags=Gio.ApplicationFlags.FLAGS_NONE,
                         **kwargs)
        self.set_resource_base_path("/io/fede/ClaudeSessionHub")

    def do_startup(self):
        Adw.Application.do_startup(self)

        # Load application CSS (includes chat bubble styles)
        css_provider = Gtk.CssProvider()
        css_provider.load_from_resource('/io/fede/ClaudeSessionHub/style.css')
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Set icons
        Gtk.IconTheme.get_for_display(
            Gdk.Display.get_default()).add_resource_path(
            "/io/fede/ClaudeSessionHub/icons"
        )

        action = Gio.SimpleAction.new("quit", None)
        action.connect("activate", self.on_quit)
        self.add_action(action)
        self.set_accels_for_action("app.quit", ["<Ctrl>q"])

    def do_activate(self, *args, **kwargs):
        win = self.get_active_window()
        if not win:
            win = MainWindow(application=self)
            group = Gtk.WindowGroup.new()
            group.add_window(win)
        win.present()

    def get_main_windows(self):
        return [w for w in self.get_windows() if isinstance(w, MainWindow)]

    def on_quit(self, _action, _param):
        self.quit()
