"""Stub the `sublime` and `sublime_plugin` modules so `subtree.py` can be
imported in a plain Python interpreter (Sublime Text is not running during
unit tests). The helpers we test do not touch these modules; they exist
only to satisfy the top-level `import sublime` / `import sublime_plugin`
statements in `subtree.py`."""

import sys
import types


def _install_sublime_stubs():
    if "sublime" not in sys.modules:
        sublime = types.ModuleType("sublime")
        sublime.error_message = lambda msg: None
        sublime.status_message = lambda msg: None
        sublime.set_timeout = lambda fn, delay=0: fn()
        sublime.set_timeout_async = lambda fn, delay=0: fn()
        sublime.ok_cancel_dialog = lambda msg, ok_title="OK": False
        sys.modules["sublime"] = sublime

    if "sublime_plugin" not in sys.modules:
        sublime_plugin = types.ModuleType("sublime_plugin")

        class WindowCommand:
            def __init__(self, window=None):
                self.window = window

        sublime_plugin.WindowCommand = WindowCommand
        sys.modules["sublime_plugin"] = sublime_plugin


_install_sublime_stubs()
