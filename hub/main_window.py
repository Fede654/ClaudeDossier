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
        self._tree_view = None
        self._welcome = None
        self._session_page = None
        self._project_page = None
        GLib.idle_add(self._load_data)

    def _load_data(self):
        import traceback
        try:
            from hub.data.session_scanner import SessionScanner
            from hub.data.tree_builder import TreeBuilder
            scanner = SessionScanner()
            self._projects = scanner.scan()
            builder = TreeBuilder()
            self._tree_root = builder.build(self._projects)
            print(f"Loaded {len(self._projects)} projects")
            self._setup_ui()
        except Exception:
            traceback.print_exc()
        return GLib.SOURCE_REMOVE

    def _setup_ui(self):
        import traceback
        try:
            self._setup_ui_inner()
        except Exception:
            traceback.print_exc()

    def _setup_ui_inner(self):
        # Welcome page
        from hub.ui.welcome_page import make_welcome_page, update_welcome_stats
        self._welcome = make_welcome_page()
        update_welcome_stats(self._welcome, self._projects)
        self.content_stack.add_named(self._welcome, 'welcome')

        # Session page
        from hub.ui.session_viewer import SessionPage
        self._session_page = SessionPage()
        self.content_stack.add_named(self._session_page, 'session')

        # Project page
        from hub.ui.project_viewer import ProjectPage
        self._project_page = ProjectPage()
        self.content_stack.add_named(self._project_page, 'project')

        # Sidebar tree
        from hub.ui.project_tree import ProjectTreeView
        self._tree_view = ProjectTreeView()
        self._tree_view.set_tree(self._tree_root)
        self._tree_view.connect('project-selected', self._on_project_selected)
        self._tree_view.connect('session-selected', self._on_session_selected)
        self.split_view.set_sidebar(self._tree_view)

        # Show welcome by default
        self.content_stack.set_visible_child_name('welcome')
        print("_setup_ui_inner complete")

    def _on_project_selected(self, _, project):
        self._project_page.load(project)
        self.content_stack.set_visible_child_name('project')

    def _on_session_selected(self, _, session):
        self._session_page.load(session)
        self.content_stack.set_visible_child_name('session')
