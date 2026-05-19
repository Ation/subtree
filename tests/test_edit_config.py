"""Tests for the Subtree `edit-config` operation.

Each test references the relevant R-codes from `docs/requirements.md` so
the link between behaviour and the authoritative spec is explicit
(per the doc-first rule in CLAUDE.md).
"""

import os
import subprocess
import sys
import tempfile
import unittest

import conftest  # noqa: F401 — installs sublime/sublime_plugin stubs

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import sublime  # noqa: E402 — provided by the conftest stub
import subtree  # noqa: E402


def _init_git_repo(path, initial_branch="master"):
    subprocess.run(
        ["git", "init", "-q", "-b", initial_branch, path],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", path, "config", "user.email", "test@example.com"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", path, "config", "user.name", "test"],
        check=True, capture_output=True,
    )
    with open(os.path.join(path, "README.md"), "w") as f:
        f.write("hello\n")
    subprocess.run(
        ["git", "-C", path, "add", "README.md"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", path, "commit", "-q", "-m", "init"],
        check=True, capture_output=True,
    )


class _FakeWindow:
    """Minimal stand-in for `sublime.Window` used by the command class."""

    def __init__(self, folders):
        self._folders = folders
        self.opened = []

    def folders(self):
        return list(self._folders)

    def open_file(self, path):
        self.opened.append(path)


class _CapturedError:
    """Context manager that captures `sublime.error_message` calls."""

    def __enter__(self):
        self.messages = []
        self._orig = sublime.error_message
        sublime.error_message = self.messages.append
        return self

    def __exit__(self, exc_type, exc, tb):
        sublime.error_message = self._orig
        return False


class TestEditConfigCommand(unittest.TestCase):
    """R070001 / R070002 / R070003 / R070004."""

    def test_r070001_errors_when_no_folder_open(self):
        window = _FakeWindow(folders=[])
        cmd = subtree.SubtreeEditConfigCommand(window)
        with _CapturedError() as cap:
            cmd.run()
        self.assertEqual(len(cap.messages), 1)
        self.assertIn("R070001", cap.messages[0])
        self.assertEqual(window.opened, [])

    def test_r070003_errors_when_no_config_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Plain directory — no subtree_config.json at or above.
            window = _FakeWindow(folders=[tmp])
            cmd = subtree.SubtreeEditConfigCommand(window)
            with _CapturedError() as cap:
                cmd.run()
            self.assertEqual(len(cap.messages), 1)
            self.assertIn("R070003", cap.messages[0])
            self.assertEqual(window.opened, [])

    def test_r070004_opens_config_in_root(self):
        """From the main worktree, the command should open the root config."""
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            subtree._do_init(tmp, "my_app", "master")
            main_dir = os.path.join(tmp, subtree.WORKTREES_DIRNAME, "master")
            window = _FakeWindow(folders=[main_dir])
            cmd = subtree.SubtreeEditConfigCommand(window)
            with _CapturedError() as cap:
                cmd.run()
            self.assertEqual(cap.messages, [])
            self.assertEqual(
                window.opened,
                [os.path.join(tmp, subtree.CONFIG_FILENAME)],
            )

    def test_r070004_finds_config_from_nested_subdir(self):
        """Walks upward from a nested directory to find the root."""
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            subtree._do_init(tmp, "my_app", "master")
            nested = os.path.join(
                tmp, subtree.WORKTREES_DIRNAME, "master", "deep", "nested"
            )
            os.makedirs(nested)
            window = _FakeWindow(folders=[nested])
            cmd = subtree.SubtreeEditConfigCommand(window)
            with _CapturedError() as cap:
                cmd.run()
            self.assertEqual(cap.messages, [])
            self.assertEqual(
                window.opened,
                [os.path.join(tmp, subtree.CONFIG_FILENAME)],
            )

    def test_r070004_does_not_validate_config(self):
        """A malformed config must still be openable for editing."""
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            subtree._do_init(tmp, "my_app", "master")
            config_path = os.path.join(tmp, subtree.CONFIG_FILENAME)
            with open(config_path, "w") as f:
                f.write("{ this is not valid json")
            main_dir = os.path.join(tmp, subtree.WORKTREES_DIRNAME, "master")
            window = _FakeWindow(folders=[main_dir])
            cmd = subtree.SubtreeEditConfigCommand(window)
            with _CapturedError() as cap:
                cmd.run()
            self.assertEqual(cap.messages, [])
            self.assertEqual(window.opened, [config_path])


if __name__ == "__main__":
    unittest.main()
