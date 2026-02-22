"""Sidebar tree — nodes own their child ListStore to prevent GC segfaults."""
from __future__ import annotations

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gio, GObject, Gtk

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
        self._committed_node = None   # last node the user actually clicked
        self._restore_timer = None    # GLib source id for hover-restore

        # Sidebar header bar — aligns with the content-pane AdwHeaderBar
        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_decoration_layout('')  # no window controls on sidebar side

        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_hexpand(True)
        self._search_entry.connect('search-changed', self._on_search)
        sidebar_header.set_title_widget(self._search_entry)

        refresh_btn = Gtk.Button()
        refresh_btn.set_icon_name('view-refresh-symbolic')
        refresh_btn.add_css_class('flat')
        refresh_btn.set_tooltip_text('Rescan folders')
        refresh_btn.connect('clicked', lambda _: self.emit('refresh-requested'))
        sidebar_header.pack_end(refresh_btn)

        # Keep a SearchBar wrapper so key-capture still works
        self._search_bar = Gtk.SearchBar()
        self._search_bar.set_key_capture_widget(self._search_entry)

        self.append(sidebar_header)

        # Index progress indicator
        self._index_label = Gtk.Label()
        self._index_label.add_css_class('caption')
        self._index_label.add_css_class('dim-label')
        self._index_label.set_margin_start(12)
        self._index_label.set_margin_top(2)
        self._index_label.set_margin_bottom(2)
        self._index_label.set_halign(Gtk.Align.START)
        self._index_label.set_visible(False)
        self.append(self._index_label)
        self._search_index = None

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
        self._list_view.set_single_click_activate(True)
        self._list_view.connect('activate', self._on_activate)

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

    def _collapse_siblings(self, expanding_row):
        """Accordion: collapse other expanded project folders at the same depth/parent."""
        model = self._selection.get_model()
        target_depth = expanding_row.get_depth()
        expanding_node = expanding_row.get_item().node

        # Locate expanding_row's position to find its parent
        n = model.get_n_items()
        expanding_pos = None
        for i in range(n):
            if model.get_item(i).get_item().node is expanding_node:
                expanding_pos = i
                break
        if expanding_pos is None:
            return

        # Parent = nearest ancestor at depth-1 before this row
        parent_node = None
        if target_depth > 0:
            for i in range(expanding_pos - 1, -1, -1):
                row = model.get_item(i)
                if row.get_depth() == target_depth - 1:
                    parent_node = row.get_item().node
                    break

        # Collect all expanded siblings (same depth, same parent, not self)
        to_collapse = []
        for i in range(model.get_n_items()):
            row = model.get_item(i)
            if row.get_depth() != target_depth:
                continue
            if row.get_item().node is expanding_node:
                continue
            if not row.get_expanded():
                continue
            # Find this row's parent
            rp_node = None
            if target_depth > 0:
                for j in range(i - 1, -1, -1):
                    r = model.get_item(j)
                    if r.get_depth() == target_depth - 1:
                        rp_node = r.get_item().node
                        break
            if rp_node is parent_node:
                to_collapse.append(row)

        for row in to_collapse:
            row.set_expanded(False)

    def _setup_row(self, factory, item):
        expander = Gtk.TreeExpander()
        box = Gtk.Box(spacing=6)
        icon = Gtk.Image()
        label = Gtk.Label(xalign=0, hexpand=True)
        label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        box.append(icon)
        box.append(label)
        expander.set_child(box)

        # Mutable cell updated by _bind_row so the motion handler sees current node
        node_cell = [None]
        expander._node_cell = node_cell
        motion = Gtk.EventControllerMotion()
        motion.connect('enter', lambda _c, _x, _y, nc=node_cell: self._on_row_hover(nc))
        motion.connect('leave', lambda _c: self._on_row_leave())
        expander.add_controller(motion)

        item.set_child(expander)

    def _bind_row(self, factory, item):
        tree_row = item.get_item()
        expander = item.get_child()
        expander.set_list_row(tree_row)

        node_obj = tree_row.get_item()
        node = node_obj.node
        expander._node_cell[0] = node  # keep motion handler in sync
        box = expander.get_child()
        icon = box.get_first_child()
        label = icon.get_next_sibling()

        if isinstance(node, SessionLeaf):
            agent = getattr(node.session, 'agent_source', 'claude')
            if agent == "codex":
                icon.set_from_icon_name('utilities-terminal-symbolic')
            elif agent == "antigravity":
                icon.set_from_icon_name('weather-clear-symbolic')
            else:
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
            self.emit('project-selected', node.project)

    def _on_activate(self, _list_view, position):
        # Cancel any pending hover-restore — user committed this selection
        if self._restore_timer is not None:
            GLib.source_remove(self._restore_timer)
            self._restore_timer = None

        model = self._selection.get_model()
        row = model.get_item(position)
        node = row.get_item().node
        self._committed_node = node  # anchor for hover-restore

        if isinstance(node, DirNode) and node.project is not None:
            new_state = not row.get_expanded()
            def _toggle(r=row, s=new_state):
                r.set_expanded(s)
                if s:
                    self._collapse_siblings(r)
                return GLib.SOURCE_REMOVE
            GLib.idle_add(_toggle)

    def _on_row_hover(self, node_cell):
        # Cancel pending restore — still hovering; single_click_activate handles preview
        if self._restore_timer is not None:
            GLib.source_remove(self._restore_timer)
            self._restore_timer = None

    def _on_row_leave(self):
        if self._restore_timer is not None:
            GLib.source_remove(self._restore_timer)
        self._restore_timer = GLib.timeout_add(120, self._restore_committed)

    def _restore_committed(self):
        self._restore_timer = None
        if self._committed_node is None:
            return GLib.SOURCE_REMOVE
        # Restoring the selection triggers selection-changed → content + scroll restore
        self._reselect_node(self._committed_node)
        return GLib.SOURCE_REMOVE

    def _reselect_node(self, target_node):
        """Find target_node in the flat model and set it as the selected item."""
        model = self._selection.get_model()
        for i in range(model.get_n_items()):
            if model.get_item(i).get_item().node is target_node:
                self._selection.set_selected(i)
                return
        # Node not visible (parent collapsed): emit directly as fallback
        if isinstance(target_node, SessionLeaf):
            self.emit('session-selected', target_node.session)
        elif isinstance(target_node, DirNode) and target_node.project is not None:
            self.emit('project-selected', target_node.project)

    def expand_all(self) -> int:
        """Expand every DirNode in the current model (used for demo/screenshot mode)."""
        if self._selection is None:
            return GLib.SOURCE_REMOVE
        model = self._selection.get_model()
        i = 0
        while i < model.get_n_items():
            row = model.get_item(i)
            if isinstance(row.get_item().node, DirNode):
                row.set_expanded(True)
            i += 1
        return GLib.SOURCE_REMOVE

    def set_search_index(self, index) -> None:
        self._search_index = index

    def update_index_progress(self, done: int, total: int) -> None:
        if done < total:
            self._index_label.set_text(f'Indexing {done} / {total}…')
            self._index_label.set_visible(True)

    def on_index_ready(self) -> None:
        self._index_label.set_visible(False)
        # Re-run search with FTS5 if query is active
        if self._search_entry.get_text().strip():
            self._on_search(None)

    def _on_search(self, _entry=None):
        import dataclasses
        query = self._search_entry.get_text().strip()
        self._current_query = query.lower()
        if not query:
            self.set_tree_root(self._root_node)
            return
        if self._all_projects is None:
            return

        q = query.lower()
        filtered = []

        if self._search_index and self._search_index.is_ready:
            matching_sids = set(self._search_index.search(query))
            for p in self._all_projects:
                if q in p.original_path.lower():
                    filtered.append(p)  # path match — show all sessions
                else:
                    hits = [s for s in p.sessions if s.session_id in matching_sids]
                    if hits:
                        filtered.append(dataclasses.replace(p, sessions=hits))
        else:
            for p in self._all_projects:
                if q in p.original_path.lower():
                    filtered.append(p)
                else:
                    hits = [s for s in p.sessions if q in s.first_prompt.lower()]
                    if hits:
                        filtered.append(dataclasses.replace(p, sessions=hits))

        filtered_root = TreeBuilder().build(filtered)
        self.set_tree_root(filtered_root)
