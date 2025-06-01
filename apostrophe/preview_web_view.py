# Copyright (C) 2022, Manuel Genovés <manuel.genoves@gmail.com>
#               2019, Gonçalo Silva
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
# END LICENSE

import math
import webbrowser
from pathlib import Path

import gi

from .helpers import get_media_path

gi.require_version('WebKit', '6.0')
from gi.repository import GObject, WebKit


class PreviewWebView(WebKit.WebView):
    """A WebView that provides read/write access to scroll.

    It does so using JavaScript, by continuously monitoring it while loaded.
    The alternative is using a WebExtension and C-bindings (see reference),
    but that is more complicated implementation-wise,
    as well as build-wise until we start building with Meson.

    Reference: https://github.com/aperezdc/webkit2gtk-python-webextension-example
    """

    __gsignals__ = {
        "rendered": (GObject.SIGNAL_RUN_LAST, None, ()),
    }

    scroll_scale_ = 0

    top_margin_ = 0

    @GObject.Property(type=float)
    def scroll_scale(self):
        return self.scroll_scale_

    @scroll_scale.setter
    def scroll_scale(self, value):
        if not math.isclose(value, self.scroll_scale_, rel_tol=1e-5):
            self.scroll_scale_ = value
            self.evaluate_javascript(f"observer.setScrollScale({value})", -1, None, None, None, None)
            self.notify("scroll_scale")

    @GObject.Property(type=float)
    def top_margin(self):
        return self.top_margin_

    @top_margin.setter
    def top_margin(self, value):
        if value != self.top_margin_:
            self.top_margin_ = value
        # sync the default 34px height with textview's
        self.evaluate_javascript(f'document.documentElement.style.setProperty("--topbars-height", "{34 + value}px");', -1, None, None, None, None)
        self.notify("top_margin")

    def __init__(self):
        super().__init__()

        self.connect("decide-policy", self.on_decide_policy)

        self.scroll_scale = 0

        script = WebKit.UserScript.new(
            Path(get_media_path("/media/js/scroll.js")).read_text(),
            WebKit.UserContentInjectedFrames.TOP_FRAME,
            WebKit.UserScriptInjectionTime.START,
            None, None
        )
        self.content_manager = self.get_user_content_manager()
        self.content_manager.add_script(script)
        self.content_manager.connect("script-message-received::scrollChanged", self.on_webview_scroll)
        self.content_manager.connect("script-message-received::rendered", self.on_rendered)
        self.content_manager.register_script_message_handler("scrollChanged", None)
        self.content_manager.register_script_message_handler("rendered", None)

    def on_webview_scroll(self, content_manager, value):
        if value.is_number():
            if not math.isclose(value.to_double(), self.scroll_scale_, rel_tol=1e-4):
                self.scroll_scale_ = value.to_double()
                self.notify("scroll_scale")

    def on_decide_policy(self, _web_view, decision, decision_type):
        if decision_type == WebKit.PolicyDecisionType.NAVIGATION_ACTION and \
                decision.get_navigation_action().is_user_gesture():
            webbrowser.open(decision.get_navigation_action().get_request().get_uri())
            decision.ignore()       # Do not follow the link in the WebView
            return True
        return False

    def on_rendered(self, *args, **kwargs):
        self.emit("rendered")
