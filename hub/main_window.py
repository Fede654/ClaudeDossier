"""Main window — Adw.OverlaySplitView hub shell."""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk


@Gtk.Template(resource_path='/io/fede/ClaudeSessionHub/ui/Window.ui')
class MainWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'MainWindow'

    split_view = Gtk.Template.Child()
    content_stack = Gtk.Template.Child()
    header_bar = Gtk.Template.Child()
    menu_button = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._projects = []
        self._tree_root = None
        GLib.idle_add(self._load_data)

    def _load_data(self):
        from hub.data.session_scanner import SessionScanner
        from hub.data.tree_builder import TreeBuilder
        scanner = SessionScanner()
        self._projects = scanner.scan()
        builder = TreeBuilder()
        self._tree_root = builder.build(self._projects)
        print(f"Loaded {len(self._projects)} projects")
        self._setup_ui()
        return GLib.SOURCE_REMOVE

    def _setup_ui(self):
        """Wire up UI components after data is loaded (expanded in Phases 4–6)."""
        pass

    def _on_project_selected(self, _, project):
        print(f"Project: {project.original_path}")

    def _on_session_selected(self, _, session):
        print(f"Session: {session.session_id}")
