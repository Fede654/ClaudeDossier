#!/usr/bin/env python
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
### BEGIN LICENSE
# Copyright (C) 2019, Wolf Vollprecht <w.vollprecht@gmail.com>
#               2021, Manuel Genovés <manuel.genoves@gmail.com>
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
### END LICENSE

import unittest
import regex as re

from apostrophe import markup_regex

def regex_tests(test_texts, regex_pattern):
    """Decorator to generate regex test cases for a unittest.TestCase method."""
    def decorator(test_method):
        def wrapper(self):
            for test, expected in test_texts.items():
                with self.subTest(test=test):
                    match = re.search(regex_pattern, test)
                    if expected is None:
                        self.assertIsNone(match, msg=f"Test failed: {test}")
                    else:
                        self.assertIsNotNone(match, msg=f"Test failed: {test}")
                        if isinstance(expected, dict):
                            for key, value in expected.items():
                                self.assertEqual(match.group(key), value,
                                                 msg=f"{test} - group '{key}'")
                        elif isinstance(expected, bool):
                            self.assertTrue(match, msg=f"Test failed: {test}")
                        else:
                            self.assertEqual(match.group("text"), expected,
                                             msg=f"{test} - text")
        return wrapper
    return decorator

class TestRegex(unittest.TestCase):
    """Test cases based on CommonMark's specs and demo:
       - https://spec.commonmark.org/
       - https://spec.commonmark.org/dingus/

       CommonMark is the Markdown variant chosen as first-class. It's great and encouraged that
       others are supported as well, but when in conflict or undecided, CommonMark should be picked.
    """

    @regex_tests(
        test_texts={
            "*italic*": "italic",
            "*i*": "i", # one letter
            "This is *italic* text": "italic", # in sentence
            "This is *1italic* text": "1italic", # starting with number
            "This is *和italic* text": "和italic", # unicode
            "before*middle*end": "middle", # within word
            "leading * space*": None, # leading space
            "This is **italic** text": None, # bold
            "This is *italic** text": None, # mismatch
            "This is \\*italic** text": None, # escaped
            "This is *italic\\* text": None, # escaped
            "This is **italic* text": None, # mismatch
            "before* middle *end": None, 
            "before* middle*end": None,
            "before*middle *end": "middle ",
            "*partial* match*": "partial", 
            "*multi\nline*": None, # shouldn't match across lines
            "empty * * italic": None # empty
        },
        regex_pattern=markup_regex.ITALIC_ASTERISK
    )
    def test_italic_asterisk(self):
        pass

    @regex_tests(
        test_texts={
            "_italic_": "italic",
            "_i_": "i", # one letter
            "This is _italic_ text": "italic", # in sentence
            "This is _1italic_ text": "1italic", # starting with number
            "This is _和italic_ text": "和italic", # unicode
            "before_middle_end": None, # within word
            "This is __italic__ text": None, # bold
            "This is __italic_ text": None, # mismatch
            "This is _italic__ text": None, # mismatch
            "before_ middle _end": None,
            "before_ middle_end": None,
            "before_middle _end": None,
            "_partial_ match_": "partial", 
            "_multi\nline_": None, # shouldn't match across lines
            "empty _ _ italic": None, # empty
        },
        regex_pattern=markup_regex.ITALIC_UNDERSCORE
    )
    def test_italic_underscore(self):
        pass

    @regex_tests(
        test_texts={
            "**bold**": "bold",
            "__bold__": "bold",
            "**b**": "b",
            "__b__": "b",
            "This is **bold** text": "bold",
            "This is **1bold** text": "1bold",
            "This is **和bold** text": "和bold",
            "This is __bold__ text": "bold",
            "before**middle**end": "middle",
            "before** middle **end": None,
            "before** middle**end": None,
            "before**middle **end": "middle ",
            "**bold__": None,
            "\\**bold**": None,
            "**multi\nline**": None, # shouldn't match across lines
            "empty * * bold": None
        },
        regex_pattern=markup_regex.BOLD
    )
    def test_bold(self):
        pass

    @regex_tests(
        test_texts={
            "**_text_**": "text",
            "***text***": "text",
            "___text___": "text",
            "__*text*__": "text",
            "__*text_**": None,
            "__*text__*": None,
            "***t***": "t",
            "___t___": "t",
            "This is ***text*** text": "text",
            "This is ***1text*** text": "1text",
            "This is ***和text*** text": "和text",
            "This is ___text___ text": "text",
            "before***middle***end": "middle",
            "before*** middle ***end": None,
            "before*** middle***end": None,
            "before***middle ***end": "middle ",
            "empty * * text": None
        },
        regex_pattern=markup_regex.BOLD_ITALIC
    )
    def test_bold_italic(self):
        pass

    @regex_tests(
        test_texts={
            "~~text~~": "text",
            "~~text text~~": "text text",
            "~~text~": None,
            "~~t~~": "t",
            "~~text ~~": None,
            "~~ text~~": None,
            "\\~~text~~": None,
            "~~text\\~~": None,
            "empty ~~ ~~ text": None
        },
        regex_pattern=markup_regex.STRIKETHROUGH
    )
    def test_strikethrough(self):
        pass

    @regex_tests(
        test_texts={
            "`code`": "code",
            "``code with ` backtick``": "code with ` backtick",
            "```multi tick```": "multi tick",
            "` leading space`": " leading space",
            "`trailing space `": "trailing space ",
            "````": None,
            "`": None,
            "`` code `": None,
            "`\nmulti line`": None
        },
        regex_pattern=markup_regex.CODE
    )
    def test_code(self):
        pass

    @regex_tests(
        test_texts={
            "[text](url)": {"text": "text", "url": "url"},
            "[test](http://example.com)": {"text": "test", "url": "http://example.com"},
            "[test](url \"title\")": {"text": "test", "url": "url", "title": "title"},
            "[empty]()": None,
            "[invalid](url": None,
            "[](url)": {"text": "", "url": "url"},
            # "[text](url \"title)": None,
            "[text] (url)": None
        },
        regex_pattern=markup_regex.LINK
    )
    def test_link(self):
        pass

    @regex_tests(
        test_texts={
            "![alt](img.jpg)": {"text": "alt", "url": "img.jpg"},
            "![test](http://example.com/image.png \"title\")": {"text": "test", "url": "http://example.com/image.png", "title": "title"},
            "![empty]()": None,
            "!invalid](url)": None,
            "![alt](url": None
        },
        regex_pattern=markup_regex.IMAGE
    )
    def test_image(self):
        pass

    @regex_tests(
        test_texts={
            "---": True,
            "***": True,
            "___": True,
            "- - -": True,
            "--": None,
            "=====": None,
            "* *": None,
            "*****": True,
            "  ***  ": True,
            "\t---\t": None,
            "-*--": None
        },
        regex_pattern=markup_regex.HORIZONTAL_RULE
    )
    def test_hr(self):
        pass

    @regex_tests(
        test_texts={
            # Valid checklist items
            "- [ ] item": {"check": " ", "text": "item"},
            "+ [X] done": {"check": "X", "text": "done"},
            # Invalid checklist items
            "- [] missing check": None,
            "[ ] standalone": None,
            "-[ ] no space": None,
            "- [x]extra": None,
        },
        regex_pattern=markup_regex.CHECKLIST
    )
    def test_checklist(self):
        pass

    @regex_tests(
        test_texts={
            "# Header 1": "Header 1",
            "## Header 2": "Header 2",
            "### Header 3": "Header 3",
            "#### Header 4": "Header 4",
            "##### Header 5": "Header 5",
            "###### Header 6": "Header 6",
            "#Header 1": None,
            " # Header 1": None,
            "#": None,
            "#######": None,
            "before\n# Header\nafter": "Header"
        },
        regex_pattern=markup_regex.HEADER
    )
    def test_header(self):
        pass

    @regex_tests(
        test_texts={
            "Header 1\n=": None, # techincally correct, but better from an usability POV
            "Header 1##\n=": None,
            "Header 1\n=\n": "Header 1",
            "Header 1##\n=\n": "Header 1##",
            "Header 2\n--  \n": "Header 2",
            "Header 1\n=f": None,
            "Header 1\n =": None
        },
        regex_pattern=markup_regex.HEADER_UNDER
    )
    def test_header_under(self):
        pass

    @regex_tests(
        test_texts={
            "- item": {"indent": "", "symbol": "-", "text": "item"},
            "\t+ item": {"indent": "\t", "symbol": "+", "text": "item"},
            "*item": None,
            "not a list": None
        },
        regex_pattern=markup_regex.LIST
    )
    def test_list(self):
        pass

    @regex_tests(
        test_texts={
            "1. item": {"indent": "", "prefix": "1.", "number": "1", "delimiter": ".", "text": "item"},
            "a) item": {"indent": "", "prefix": "a)", "delimiter": ")", "text": "item"},
            "    2) indented": {"indent": "    ", "prefix": "2)", "number": "2", "delimiter": ")", "text": "indented"},
            "1 item": None
        },
        regex_pattern=markup_regex.ORDERED_LIST
    )
    def test_ordered_list(self):
        pass

    @regex_tests(
        test_texts={
            "> blockquote": "blockquote",
            "   > spaced blockquote": "spaced blockquote",
            "no blockquote": None
        },
        regex_pattern=markup_regex.BLOCK_QUOTE
    )
    def test_block_quote(self):
        pass

    @regex_tests(
        test_texts={
            "```code block```": "code block",
            "~~~example~~~": "example",
            "```not closed": None
        },
        regex_pattern=markup_regex.CODE_BLOCK
    )
    def test_code_block(self):
        pass

    @regex_tests(
        test_texts={
            "$a$": "a",
            "$ab$": "ab",
            "$a b$": "a b",
            "$ a$": None,
            "$abc": None,
            "$$math$$": "math"
        },
        regex_pattern=markup_regex.MATH
    )
    def test_math(self):
        pass

    @regex_tests(
        test_texts={
            "ref[^1]": {"text": "ref", "id": "1"},
            "note[^note]": {"text": "note", "id": "note"},
            "[^id]": None
        },
        regex_pattern=markup_regex.FOOTNOTE_ID
    )
    def test_footnote_id(self):
        pass

    @regex_tests(
        test_texts={
            "[^1]: This is a footnote.\n": {"id": "1", "text": "This is a footnote."},
            "  [^note]:  Footnote text\n": {"id": "note", "text": "Footnote text"},
            "[^2]: First line\n    second line\n": {"id": "2", "text": "First line\n    second line"},
            "Not a footnote": None
        },
        regex_pattern=markup_regex.FOOTNOTE
    )
    def test_footnote(self):
        pass

    @regex_tests(
        test_texts={
            "---\ntitle: Test\ndate: 2025-03-06\n---\n": "title: Test\ndate: 2025-03-06",
            "---\ntitle: Another\ndate: 2025-03-06\n...\n": "title: Another\ndate: 2025-03-06",
            "----\ntitle: Test\ntitle: Test\n----\n": None
        },
        regex_pattern=markup_regex.FRONTMATTER
    )
    def test_frontmatter(self):
        pass

if __name__ == '__main__':
    unittest.main()
