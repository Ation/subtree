"""Tests for the Subtree `switch` operation.

Each test references the relevant R-codes from `docs/requirements.md` so
the link between behaviour and the authoritative spec is explicit
(per the doc-first rule in CLAUDE.md).
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import conftest  # noqa: F401 — installs sublime/sublime_plugin stubs

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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


def _make_subtree_repo(tmp, repo_name="my_app", branch="master"):
    _init_git_repo(tmp, initial_branch=branch)
    subtree._do_init(tmp, repo_name, branch)
    with open(os.path.join(tmp, subtree.CONFIG_FILENAME)) as f:
        config = json.load(f)
    main_dir = os.path.join(tmp, subtree.WORKTREES_DIRNAME, branch)
    return tmp, config, main_dir


class TestIdentifyCurrentWorktree(unittest.TestCase):
    """R050005: locate the worktree that contains a given folder."""

    def _config(self, names):
        """Tiny config stub — only `worktrees[].name` is read by the helper."""
        return {"worktrees": [{"name": n} for n in names]}

    def test_returns_name_when_folder_is_the_worktree_dir(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "worktrees", "master"))
            cfg = self._config(["master"])
            folder = os.path.join(root, "worktrees", "master")
            self.assertEqual(subtree._identify_current_worktree(folder, root, cfg), "master")

    def test_returns_name_when_folder_is_subdir_of_worktree(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "worktrees", "master", "src"))
            cfg = self._config(["master"])
            folder = os.path.join(root, "worktrees", "master", "src")
            self.assertEqual(subtree._identify_current_worktree(folder, root, cfg), "master")

    def test_prefers_longer_match_for_nested_branches(self):
        """A folder under `feature/foo` must not be reported as `feature`."""
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "worktrees", "feature", "foo"))
            cfg = self._config(["feature", "feature/foo"])
            folder = os.path.join(root, "worktrees", "feature", "foo")
            self.assertEqual(
                subtree._identify_current_worktree(folder, root, cfg),
                "feature/foo",
            )

    def test_returns_none_when_folder_is_root(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "worktrees", "master"))
            cfg = self._config(["master"])
            self.assertIsNone(subtree._identify_current_worktree(root, root, cfg))

    def test_returns_none_when_folder_is_outside_worktrees(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "worktrees", "master"))
            os.makedirs(os.path.join(root, "elsewhere"))
            cfg = self._config(["master"])
            folder = os.path.join(root, "elsewhere")
            self.assertIsNone(subtree._identify_current_worktree(folder, root, cfg))

    def test_returns_none_when_worktrees_has_no_matching_entry(self):
        """Folder under worktrees/ but no entry in config — defensive None."""
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "worktrees", "stray"))
            cfg = self._config(["master"])
            folder = os.path.join(root, "worktrees", "stray")
            self.assertIsNone(subtree._identify_current_worktree(folder, root, cfg))


class TestSwitchFiltering(unittest.TestCase):
    """R050006: the current worktree is excluded from the candidate list."""

    def test_current_worktree_excluded_when_in_main(self):
        """When invoked from the main worktree, only siblings should appear."""
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            # Add a couple of fabricated entries so the list is non-trivial.
            config["worktrees"].extend([
                {"name": "feature_a", "created_from": "master",
                 "project_file": "my_app_feature_a.sublime-project"},
                {"name": "feature/foo", "created_from": "master",
                 "project_file": "my_app_feature__foo.sublime-project"},
            ])
            current = subtree._identify_current_worktree(main_dir, root, config)
            self.assertEqual(current, "master")

            candidates = [wt for wt in config["worktrees"] if wt["name"] != current]
            names = [c["name"] for c in candidates]
            self.assertEqual(names, ["feature_a", "feature/foo"])

    def test_current_worktree_excluded_when_in_nested_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            os.makedirs(os.path.join(root, "worktrees", "feature", "foo"))
            config["worktrees"].append({
                "name": "feature/foo", "created_from": "master",
                "project_file": "my_app_feature__foo.sublime-project",
            })
            folder = os.path.join(root, "worktrees", "feature", "foo")
            current = subtree._identify_current_worktree(folder, root, config)
            self.assertEqual(current, "feature/foo")

            candidates = [wt for wt in config["worktrees"] if wt["name"] != current]
            self.assertEqual([c["name"] for c in candidates], ["master"])

    def test_no_current_worktree_means_full_list(self):
        """If invoked from the root (or anywhere outside worktrees/), nothing is dropped."""
        with tempfile.TemporaryDirectory() as tmp:
            root, config, _ = _make_subtree_repo(tmp)
            config["worktrees"].append({
                "name": "feature_a", "created_from": "master",
                "project_file": "my_app_feature_a.sublime-project",
            })
            current = subtree._identify_current_worktree(root, root, config)
            self.assertIsNone(current)
            candidates = [wt for wt in config["worktrees"] if wt["name"] != current]
            self.assertEqual(
                [c["name"] for c in candidates],
                ["master", "feature_a"],
            )


if __name__ == "__main__":
    unittest.main()
