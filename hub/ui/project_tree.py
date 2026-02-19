"""Sidebar tree — nodes own their child ListStore to prevent GC segfaults."""
from __future__ import annotations

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import GLib, Gio, GObject, Gtk

from hub.data.tree_builder import DirNode, SessionLeaf, TreeBuilder


class NodeObject(GObject.Object):
    __gtype_name__ = 'NodeObject'

    def __init__(self, node):
        super().__init__()
        self.node = node
        # GC safety: own the child store on this object
        if hasattr(node, 'children') and node.children:
            self._children_store = Gio.ListStore.new(NodeObject)
            for child in node.children:
                self._children_store.append(NodeObject(child))
        else:
            self._children_store = None


class ProjectTreeView(Gtk.Box):
    __gtype_name__ = 'ProjectTreeView'
    __gsignals__ = {
        'project-selected': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        'session-selected': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        'refresh-requested': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._root_store = None
        self._root_node = None
        self._all_projects = None
        self._current_query = ""
        self._list_view = None
        self._selection = None

        # Search bar + refresh button
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._search_bar = Gtk.SearchBar()
        self._search_bar.set_hexpand(True)
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.connect('search-changed', self._on_search)
        self._search_bar.set_child(self._search_entry)
        self._search_bar.set_search_mode(True)
        top.append(self._search_bar)

        refresh_btn = Gtk.Button()
        refresh_btn.set_icon_name('view-refresh-symbolic')
        refresh_btn.add_css_class('flat')
        refresh_btn.set_tooltip_text('Rescan folders')
        refresh_btn.connect('clicked', lambda _: self.emit('refresh-requested'))
        top.append(refresh_btn)

        self.append(top)

        # Scrolled window placeholder (filled by set_tree)
        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_vexpand(True)
        self.append(self._scroll)

    def set_tree(self, root: DirNode) -> None:
        self._root_node = root
        self._all_projects = self._collect_projects(root)
        self._build_list(root)

    def set_tree_root(self, root: DirNode) -> None:
        """Rebuild with a (possibly filtered) root without touching _all_projects."""
        self._build_list(root)

    def _collect_projects(self, node) -> list:
        if isinstance(node, SessionLeaf):
            return []
        result = []
        if isinstance(node, DirNode) and node.project is not None:
            result.append(node.project)
        for child in getattr(node, 'children', []):
            result.extend(self._collect_projects(child))
        return result

    def _build_list(self, root: DirNode) -> None:
        self._root_store = Gio.ListStore.new(NodeObject)
        for child in root.children:
            self._root_store.append(NodeObject(child))

        def create_children(item):
            return item._children_store

        tree_model = Gtk.TreeListModel.new(
            root=self._root_store,
            passthrough=False,
            autoexpand=False,
            create_func=create_children,
        )

        self._selection = Gtk.SingleSelection.new(tree_model)
        self._selection.connect('selection-changed', self._on_selection_changed)

        factory = Gtk.SignalListItemFactory()
        factory.connect('setup', self._setup_row)
        factory.connect('bind', self._bind_row)

        self._list_view = Gtk.ListView.new(self._selection, factory)
        self._list_view.add_css_class('navigation-sidebar')

        self._scroll.set_child(self._list_view)
        GLib.idle_add(self._auto_expand_containers)

    def _auto_expand_containers(self):
        """Expand all pure container nodes (no project) so e.g. REPOS/ opens by default."""
        model = self._selection.get_model()  # TreeListModel
        i = 0
        while i < model.get_n_items():
            row = model.get_item(i)
            node = row.get_item().node
            if isinstance(node, DirNode) and node.project is None:
                row.set_expanded(True)
            i += 1
        return GLib.SOURCE_REMOVE

    def _setup_row(self, factory, item):
        expander = Gtk.TreeExpander()
        box = Gtk.Box(spacing=6)
        icon = Gtk.Image()
        label = Gtk.Label(xalign=0, hexpand=True)
        label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        box.append(icon)
        box.append(label)
        expander.set_child(box)
        item.set_child(expander)

    def _bind_row(self, factory, item):
        tree_row = item.get_item()
        expander = item.get_child()
        expander.set_list_row(tree_row)

        node_obj = tree_row.get_item()
        node = node_obj.node
        box = expander.get_child()
        icon = box.get_first_child()
        label = icon.get_next_sibling()

        if isinstance(node, SessionLeaf):
            icon.set_from_icon_name('text-x-generic-symbolic')
            label.set_text(node.name)
        elif node.project is not None:
            icon.set_from_icon_name('folder-symbolic')
            label.set_text(f"{node.name}  ({node.session_count})")
        else:
            icon.set_from_icon_name('folder-open-symbolic')
            label.set_text(f"{node.name}  ({node.session_count})")

    def _on_selection_changed(self, selection, _pos, _n):
        item = selection.get_selected_item()
        if item is None:
            return
        node = item.get_item().node
        if isinstance(node, SessionLeaf):
            self.emit('session-selected', node.session)
        elif isinstance(node, DirNode) and node.project is not None:
            item.set_expanded(not item.get_expanded())
            self.emit('project-selected', node.project)

    def _on_search(self, entry):
        query = entry.get_text().lower().strip()
        self._current_query = query
        if not query:
            self.set_tree_root(self._root_node)
            return
        if self._all_projects is None:
            return
        filtered = [
            p for p in self._all_projects
            if query in p.original_path.lower()
            or any(query in s.first_prompt.lower() for s in p.sessions)
        ]
        filtered_root = TreeBuilder().build(filtered)
        self.set_tree_root(filtered_root)
