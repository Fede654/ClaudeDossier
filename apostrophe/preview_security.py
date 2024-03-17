import re
from enum import IntEnum

from apostrophe.settings import Settings


class PreviewSecurity(IntEnum):
    ASK = 0
    RESTRICTED = 1
    UNRESTRICTED = 2
    UNDETERMINED = 3

class PreviewSecurityHandler:

    def __init__(self, window):
        self.settings = Settings.new()
        self.window = window

        self.window.current.connect("notify::security-level", self.on_file_security_level_changed)

    def set_file_security_level(self, level=None):
        if level:
            self.window.current.security_level = level
        else:
            if self.settings.get_enum("preview-security") == PreviewSecurity.ASK:
                self.window.current.security_level = PreviewSecurity.UNDETERMINED
            else:
                self.window.current.security_level = self.settings.get_enum("preview-security")

    def on_file_security_level_changed(self, *args, **kwargs):
        match self.window.current.security_level:
            case PreviewSecurity.ASK:
                self.window.preview_stack.set_visible_child(self.window.security_warning)
            case PreviewSecurity.RESTRICTED:
                self.window.preview_stack.set_visible_child(self.window.preview_spinner)
                self.window.preview_handler.refresh_preview()
                pass
            case PreviewSecurity.UNRESTRICTED:
                self.window.preview_stack.set_visible_child(self.window.preview_spinner)
                self.window.preview_handler.refresh_preview()
                pass
            case PreviewSecurity.UNDETERMINED:
                self.window.preview_stack.set_visible_child(self.window.preview_spinner)

    def assert_security_risk(self, text):
        if self.settings.get_enum("preview-security") != PreviewSecurity.ASK:
            return

        tags = [
            "<!DOCTYPE", "<a", "<abbr", "<acronym", "<address", "<applet", "<area", "<article", "<aside", 
            "<audio", "<b", "<base", "<basefont", "<bdi", "<bdo", "<big", "<blockquote", "<body", "<br", 
            "<button", "<canvas", "<caption", "<center", "<cite", "<code", "<col", "<colgroup", "<data", 
            "<datalist", "<dd", "<del", "<details", "<dfn", "<dialog", "<dir", "<div", "<dl", "<dt", "<em", 
            "<embed", "<fieldset", "<figcaption", "<figure", "<font", "<footer", "<form", "<frame", "<frameset", 
            "<h", "<head", "<header", "<hgroup", "<hr", "<html", "<i", "<iframe", "<img", "<input", "<ins", 
            "<kbd", "<label", "<legend", "<li", "<link", "<main", "<map", "<mark", "<menu", "<meta", "<meter", 
            "<nav", "<noframes", "<noscript", "<object", "<ol", "<optgroup", "<option", "<output", "<p", 
            "<param", "<picture", "<pre", "<progress", "<q", "<rp", "<rt", "<ruby", "<s", "<samp", "<script", 
            "<search", "<section", "<select", "<small", "<source", "<span", "<strike", "<strong", "<style", 
            "<sub", "<summary", "<sup", "<svg", "<table", "<tbody", "<td", "<template", "<textarea", "<tfoot", 
            "<th", "<thead", "<time", "<title", "<tr", "<track", "<tt", "<u", "<ul", "<var", "<video", "<wbr",
        ]

        tags_re = re.compile("|".join(tags), re.I)
        result = re.search(tags_re, text)
        if result:
            self.window.current.security_level = PreviewSecurity.ASK
        else:
            self.window.current.security_level = PreviewSecurity.RESTRICTED
