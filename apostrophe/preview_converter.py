from queue import Queue
from threading import Thread

from gi.repository import GLib

from apostrophe import helpers
from apostrophe.settings import Settings
from apostrophe.theme_switcher import Theme, ThemeSwitcher


class PreviewConverter:
    """Converts markdown to html using a background thread."""

    def __init__(self):
        super().__init__()

        self.queue = Queue()
        worker = Thread(target=self.__do_convert, name="preview-converter")
        worker.daemon = True
        worker.start()

    def convert(self, text, secure_preview, base_path, callback, *user_data):
        """Converts text to html, calling callback when done.

        The callback argument contains the result."""

        self.queue.put((text, secure_preview, base_path, callback, user_data))

    def stop(self):
        """Stops the background worker.
        PreviewConverter shouldn't be used after this."""

        self.queue.put((None, None))

    def __do_convert(self):
        while True:
            while True:
                (text, secure_preview, base_path, callback, user_data) = self.queue.get()
                if text is None and callback is None:
                    return
                if self.queue.empty():
                    break
            if secure_preview:
                fr = "markdown-raw_html"
            else:
                fr = Settings.new().get_value('input-format').get_string() or "markdown"

            args = ['--metadata=pagetitle:""',
                    '--standalone',
                    '--mathjax',
                    '--css=' + Theme.get_current().web_css,
                    '--metadata=base_path:' + base_path,
                    '--lua-filter=' +
                    helpers.get_media_path('/lua/relative_to_absolute.lua')]

            if Theme.get_current().name == "dark":
                args.append ('--highlight-style=breezedark')

            text = helpers.pandoc_convert(text, fr=fr, to="html5", args=args)

            GLib.idle_add(callback, text, *user_data)
