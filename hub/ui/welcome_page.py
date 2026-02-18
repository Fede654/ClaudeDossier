"""Welcome page — stats overview shown on startup."""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk

from hub.data.session_scanner import ProjectInfo


def make_welcome_page() -> Adw.StatusPage:
    """Create an Adw.StatusPage welcome widget (StatusPage is final, not subclassable)."""
    page = Adw.StatusPage()
    page.set_icon_name('document-open-recent-symbolic')
    page.set_title('Claude Session Hub')
    page.set_description('Loading…')
    return page


def update_welcome_stats(page: Adw.StatusPage, projects: list[ProjectInfo]) -> None:
    total = sum(len(p.sessions) for p in projects)
    all_s = [s for p in projects for s in p.sessions]
    if not all_s:
        page.set_description('No sessions found.\nStart a Claude Code session to see it here.')
        return
    last = max(all_s, key=lambda s: s.modified)
    last_str = last.modified.strftime('%Y-%m-%d %H:%M')
    total_msgs = sum(s.message_count for s in all_s)
    page.set_description(
        f'{len(projects)} projects  ·  {total} sessions  ·  {total_msgs:,} messages\n'
        f'Last active: {last_str}'
    )
