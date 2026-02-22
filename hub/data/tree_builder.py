"""Builds display tree from flat ProjectInfo list — zero gi imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from hub.data.session_scanner import ProjectInfo, SessionInfo


@dataclass
class DirNode:
    name: str
    full_path: str
    project: ProjectInfo | None = None
    children: list = field(default_factory=list)

    @property
    def last_active(self) -> datetime:
        if self.project:
            return self.project.last_active
        if not self.children:
            return datetime.min.replace(tzinfo=timezone.utc)
        return max(c.last_active for c in self.children)

    @property
    def session_count(self) -> int:
        if self.project:
            return len(self.project.sessions)
        return sum(c.session_count for c in self.children)


@dataclass
class SessionLeaf:
    session: SessionInfo

    @property
    def name(self) -> str:
        date = self.session.modified.strftime("%m-%d")
        prompt = self.session.first_prompt[:45].replace("\n", " ")
        return f"{date}  {prompt}"

    @property
    def last_active(self) -> datetime:
        return self.session.modified

    @property
    def session_count(self) -> int:
        return 1

    @property
    def children(self) -> list:
        return []


class TreeBuilder:
    def __init__(self, base: str | None = None, compact: bool = True):
        self.base = (base or str(Path.home())).rstrip("/")
        self.compact = compact

    def build(self, projects: list[ProjectInfo]) -> DirNode:
        root = DirNode(name="", full_path=self.base)
        for proj in projects:
            self._insert(root, proj)
        self._sort(root)
        if self.compact:
            self._compact(root)
        self._attach_leaves(root)
        return root

    def _insert(self, root: DirNode, proj: ProjectInfo) -> None:
        path = proj.original_path
        if path.startswith(self.base + "/"):
            rel = path[len(self.base) + 1:]
        else:
            rel = path.lstrip("/")
        parts = rel.split("/")
        node = root
        for i, part in enumerate(parts):
            full = self.base + "/" + "/".join(parts[:i + 1])
            match = next((c for c in node.children if isinstance(c, DirNode) and c.full_path == full), None)
            if match is None:
                match = DirNode(name=part, full_path=full)
                node.children.append(match)
            node = match
        if node.project is None:
            node.project = proj
        else:
            node.project.sessions.extend(proj.sessions)

    def _sort(self, node: DirNode) -> None:
        node.children.sort(key=lambda c: c.last_active, reverse=True)
        for child in node.children:
            if isinstance(child, DirNode):
                self._sort(child)

    def _compact(self, node: DirNode) -> None:
        for child in node.children:
            if isinstance(child, DirNode):
                self._compact(child)
        changed = True
        while changed:
            changed = False
            new_children = []
            for child in node.children:
                if (isinstance(child, DirNode)
                        and child.project is None
                        and len(child.children) == 1
                        and isinstance(child.children[0], DirNode)
                        and child.children[0].project is None):
                    gc = child.children[0]
                    gc.name = child.name + "/" + gc.name
                    new_children.append(gc)
                    changed = True
                else:
                    new_children.append(child)
            node.children = new_children

    def _attach_leaves(self, node: DirNode) -> None:
        if node.project:
            leaves = [SessionLeaf(s) for s in node.project.sessions]
            leaves.sort(key=lambda lf: lf.last_active, reverse=True)
            node.children.extend(leaves)
        for child in node.children:
            if isinstance(child, DirNode):
                self._attach_leaves(child)
