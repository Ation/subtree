"""Tests for the Subtree `init` operation.

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
    """Create a git repo at `path` on branch `initial_branch` with one commit."""
    subprocess.run(
        ["git", "init", "-q", "-b", initial_branch, path],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", path, "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", path, "config", "user.name", "test"],
        check=True,
        capture_output=True,
    )
    with open(os.path.join(path, "README.md"), "w") as f:
        f.write("hello\n")
    subprocess.run(
        ["git", "-C", path, "add", "README.md"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", path, "commit", "-q", "-m", "init"],
        check=True,
        capture_output=True,
    )


class TestValidateRepoName(unittest.TestCase):
    """R020006 — repository name must be non-empty and free of /, \\, ctrl chars."""

    def test_rejects_empty(self):
        self.assertIsNotNone(subtree._validate_repo_name(""))

    def test_rejects_forward_slash(self):
        self.assertIsNotNone(subtree._validate_repo_name("foo/bar"))

    def test_rejects_backslash(self):
        self.assertIsNotNone(subtree._validate_repo_name("foo\\bar"))

    def test_rejects_control_char(self):
        self.assertIsNotNone(subtree._validate_repo_name("foo\nbar"))
        self.assertIsNotNone(subtree._validate_repo_name("foo\x00bar"))

    def test_accepts_plain_identifier(self):
        self.assertIsNone(subtree._validate_repo_name("my_app"))
        self.assertIsNone(subtree._validate_repo_name("my-app.v2"))
        self.assertIsNone(subtree._validate_repo_name("My App"))


class TestGitBranch(unittest.TestCase):
    """R020009 — detect current branch; detached HEAD returns None."""

    def test_returns_current_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp, initial_branch="main")
            self.assertEqual(subtree._git_branch(tmp), "main")

    def test_returns_none_on_detached_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            sha = subprocess.run(
                ["git", "-C", tmp, "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "-C", tmp, "checkout", "-q", "--detach", sha],
                check=True, capture_output=True,
            )
            self.assertIsNone(subtree._git_branch(tmp))


class TestPreflight(unittest.TestCase):

    def test_r020001_rejects_dir_without_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            err, rcode = subtree._preflight(tmp)
            self.assertIsNotNone(err)
            self.assertEqual(rcode, "R020001")

    def test_accepts_plain_git_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            err, rcode = subtree._preflight(tmp)
            self.assertIsNone(err)
            self.assertIsNone(rcode)

    def test_r020007_rejects_already_initialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            with open(os.path.join(tmp, subtree.CONFIG_FILENAME), "w") as f:
                f.write("{}")
            err, rcode = subtree._preflight(tmp)
            self.assertEqual(rcode, "R020007")

    def test_r020008_rejects_reserved_worktrees_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            os.mkdir(os.path.join(tmp, "worktrees"))
            err, rcode = subtree._preflight(tmp)
            self.assertEqual(rcode, "R020008")

    def test_r020008_rejects_reserved_sublime_projects_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            os.mkdir(os.path.join(tmp, "sublime_projects"))
            err, rcode = subtree._preflight(tmp)
            self.assertEqual(rcode, "R020008")


class TestDoInit(unittest.TestCase):
    """R020002, R020003, R010002 — end-to-end conversion."""

    def test_layout_matches_structure_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp, initial_branch="master")
            # Add a subdir and another file to verify everything moves.
            os.mkdir(os.path.join(tmp, "src"))
            with open(os.path.join(tmp, "src", "main.py"), "w") as f:
                f.write("x = 1\n")
            with open(os.path.join(tmp, "extra.txt"), "w") as f:
                f.write("extra\n")

            project_path = subtree._do_init(tmp, "my_app", "master")

            # Top-level: only worktrees/, sublime_projects/, subtree_config.json.
            self.assertEqual(
                sorted(os.listdir(tmp)),
                ["sublime_projects", "subtree_config.json", "worktrees"],
            )

            # Main worktree dir name == branch name (R010002).
            wt = os.path.join(tmp, "worktrees", "master")
            self.assertTrue(os.path.isdir(wt))

            # Original contents (incl. .git) moved into the worktree (R020003.3).
            self.assertTrue(os.path.isdir(os.path.join(wt, ".git")))
            self.assertTrue(os.path.isfile(os.path.join(wt, "README.md")))
            self.assertTrue(os.path.isfile(os.path.join(wt, "extra.txt")))
            self.assertTrue(os.path.isfile(os.path.join(wt, "src", "main.py")))

            # git still functional inside the worktree (i.e. .git moved cleanly).
            subprocess.run(
                ["git", "-C", wt, "rev-parse", "--show-toplevel"],
                check=True, capture_output=True,
            )

            # Returned path points at the sublime-project file.
            self.assertEqual(
                project_path,
                os.path.join(tmp, "sublime_projects", "my_app_master.sublime-project"),
            )

    def test_r020002_main_worktree_recorded_in_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp, initial_branch="develop")
            subtree._do_init(tmp, "my_app", "develop")

            with open(os.path.join(tmp, "subtree_config.json")) as f:
                config = json.load(f)

            self.assertEqual(config["meta_information"]["repository_name"], "my_app")
            self.assertEqual(config["meta_information"]["main_worktree"], "develop")
            self.assertEqual(len(config["worktrees"]), 1)
            wt_entry = config["worktrees"][0]
            self.assertEqual(wt_entry["name"], "develop")
            self.assertIsNone(wt_entry["created_from"])
            self.assertEqual(
                wt_entry["project_file"], "my_app_develop.sublime-project"
            )

    def test_sublime_project_file_uses_absolute_worktree_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp, initial_branch="master")
            subtree._do_init(tmp, "my_app", "master")

            project_file = os.path.join(
                tmp, "sublime_projects", "my_app_master.sublime-project"
            )
            with open(project_file) as f:
                project = json.load(f)

            expected_path = os.path.join(tmp, "worktrees", "master")
            self.assertEqual(project, {"folders": [{"path": expected_path}]})
            self.assertTrue(os.path.isabs(project["folders"][0]["path"]))


if __name__ == "__main__":
    unittest.main()
