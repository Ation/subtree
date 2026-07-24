"""Tests for the Subtree `remove` operation.

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


def _add_worktree(root, config, main_dir, branch_name):
    """Use `_do_create` to add a fresh worktree branched off master."""
    source_project = os.path.join(
        root, subtree.SUBLIME_PROJECTS_DIRNAME, "my_app_master.sublime-project"
    )
    template = subtree._load_source_template(source_project)
    new_worktree_dir = os.path.join(root, subtree.WORKTREES_DIRNAME, branch_name)
    project_filename = subtree._branch_to_project_filename("my_app", branch_name)
    new_project_path = os.path.join(
        root, subtree.SUBLIME_PROJECTS_DIRNAME, project_filename
    )
    subtree._do_create(
        main_dir, "master", template,
        new_worktree_dir, new_project_path,
        branch_name, "master", project_filename, root, config,
    )
    return new_worktree_dir, new_project_path


class TestCheckUncommittedChanges(unittest.TestCase):
    """R060008 — `git status --porcelain` non-empty -> error."""

    def test_clean_repo_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            self.assertIsNone(subtree._check_uncommitted_changes(tmp))

    def test_modified_tracked_file_is_uncommitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            with open(os.path.join(tmp, "README.md"), "a") as f:
                f.write("more\n")
            self.assertIsNotNone(subtree._check_uncommitted_changes(tmp))

    def test_staged_file_is_uncommitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            with open(os.path.join(tmp, "new.txt"), "w") as f:
                f.write("x")
            subprocess.run(
                ["git", "-C", tmp, "add", "new.txt"],
                check=True, capture_output=True,
            )
            self.assertIsNotNone(subtree._check_uncommitted_changes(tmp))

    def test_untracked_file_is_uncommitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            with open(os.path.join(tmp, "extra.txt"), "w") as f:
                f.write("x")
            self.assertIsNotNone(subtree._check_uncommitted_changes(tmp))

    def test_gitignored_file_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            with open(os.path.join(tmp, ".gitignore"), "w") as f:
                f.write("*.venv/\n")
            subprocess.run(
                ["git", "-C", tmp, "add", ".gitignore"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "commit", "-q", "-m", "gitignore"],
                check=True, capture_output=True,
            )
            # Create a gitignored directory.
            os.mkdir(os.path.join(tmp, ".venv"))
            with open(os.path.join(tmp, ".venv", "cfg"), "w") as f:
                f.write("x")
            # The wildcard makes .venv match; pattern in .gitignore was '*.venv/'
            # which doesn't actually match '.venv/'. Use plain `.venv/` instead.
            with open(os.path.join(tmp, ".gitignore"), "w") as f:
                f.write(".venv/\n")
            subprocess.run(
                ["git", "-C", tmp, "add", ".gitignore"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "commit", "-q", "-m", "gitignore2"],
                check=True, capture_output=True,
            )
            self.assertIsNone(subtree._check_uncommitted_changes(tmp))


class TestCheckUpstream(unittest.TestCase):
    """R060009 / R060010."""

    def test_no_upstream_no_unique_commits(self):
        """Branch with no upstream but every commit also reachable from master."""
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            subprocess.run(
                ["git", "-C", tmp, "branch", "feature"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "checkout", "-q", "feature"],
                check=True, capture_output=True,
            )
            status = subtree._check_upstream(tmp)
            self.assertEqual(status["status"], "no_upstream")
            self.assertFalse(status["has_unique_commits"])

    def test_no_upstream_with_unique_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            subprocess.run(
                ["git", "-C", tmp, "checkout", "-q", "-b", "feature"],
                check=True, capture_output=True,
            )
            with open(os.path.join(tmp, "extra.txt"), "w") as f:
                f.write("x")
            subprocess.run(
                ["git", "-C", tmp, "add", "extra.txt"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "commit", "-q", "-m", "extra"],
                check=True, capture_output=True,
            )
            status = subtree._check_upstream(tmp)
            self.assertEqual(status["status"], "no_upstream")
            self.assertTrue(status["has_unique_commits"])

    def test_upstream_in_sync_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            sha = subprocess.run(
                ["git", "-C", tmp, "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "-C", tmp, "remote", "add", "origin",
                 "https://example.invalid/x.git"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "update-ref", "refs/remotes/origin/master", sha],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "branch", "--set-upstream-to=origin/master", "master"],
                check=True, capture_output=True,
            )
            self.assertEqual(subtree._check_upstream(tmp), {"status": "ok"})

    def test_upstream_ahead_reports_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            sha = subprocess.run(
                ["git", "-C", tmp, "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "-C", tmp, "remote", "add", "origin",
                 "https://example.invalid/x.git"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "update-ref", "refs/remotes/origin/master", sha],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "branch", "--set-upstream-to=origin/master", "master"],
                check=True, capture_output=True,
            )
            # Add 2 commits ahead.
            for i in range(2):
                with open(os.path.join(tmp, "c{}.txt".format(i)), "w") as f:
                    f.write(str(i))
                subprocess.run(
                    ["git", "-C", tmp, "add", "c{}.txt".format(i)],
                    check=True, capture_output=True,
                )
                subprocess.run(
                    ["git", "-C", tmp, "commit", "-q", "-m", "c{}".format(i)],
                    check=True, capture_output=True,
                )
            status = subtree._check_upstream(tmp)
            self.assertEqual(status["status"], "ahead")
            self.assertEqual(status["ahead_count"], 2)


class TestFindPipfileDirs(unittest.TestCase):
    """Pure file walk -- no subprocess invocation."""

    def test_empty_when_no_pipfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(list(subtree._find_pipfile_dirs(tmp)), [])

    def test_finds_pipfile_at_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "Pipfile"), "w") as f:
                f.write("")
            self.assertEqual(
                list(subtree._find_pipfile_dirs(tmp)),
                [tmp],
            )

    def test_finds_nested_pipfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            sub = os.path.join(tmp, "service")
            os.mkdir(sub)
            with open(os.path.join(sub, "Pipfile"), "w") as f:
                f.write("")
            self.assertEqual(
                list(subtree._find_pipfile_dirs(tmp)),
                [sub],
            )

    def test_finds_multiple(self):
        with tempfile.TemporaryDirectory() as tmp:
            for sub in ("a", "b"):
                d = os.path.join(tmp, sub)
                os.mkdir(d)
                with open(os.path.join(d, "Pipfile"), "w") as f:
                    f.write("")
            self.assertEqual(
                sorted(subtree._find_pipfile_dirs(tmp)),
                sorted([os.path.join(tmp, "a"), os.path.join(tmp, "b")]),
            )


class TestFindComposeDirs(unittest.TestCase):
    """R060017 — pure file walk, no subprocess invocation."""

    def test_empty_when_no_compose_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(list(subtree._find_compose_dirs(tmp)), [])

    def test_finds_each_recognised_filename(self):
        for name in subtree.COMPOSE_FILENAMES:
            with tempfile.TemporaryDirectory() as tmp:
                with open(os.path.join(tmp, name), "w") as f:
                    f.write("")
                self.assertEqual(
                    list(subtree._find_compose_dirs(tmp)),
                    [tmp],
                    "expected {} to mark a compose dir".format(name),
                )

    def test_finds_nested_compose_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            sub = os.path.join(tmp, "service")
            os.mkdir(sub)
            with open(os.path.join(sub, "docker-compose.yml"), "w") as f:
                f.write("")
            self.assertEqual(list(subtree._find_compose_dirs(tmp)), [sub])

    def test_yields_dir_once_when_multiple_compose_files_present(self):
        """A dir with both a base and an override file is yielded a single time."""
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("docker-compose.yml", "docker-compose.yaml"):
                with open(os.path.join(tmp, name), "w") as f:
                    f.write("")
            self.assertEqual(list(subtree._find_compose_dirs(tmp)), [tmp])


class TestCleanupPipenvEnvs(unittest.TestCase):
    """R060012 — pipenv invocation; graceful skip when pipenv is missing."""

    def _patch_subprocess_run(self, replacement):
        original = subtree.subprocess.run
        subtree.subprocess.run = replacement
        self.addCleanup(lambda: setattr(subtree.subprocess, "run", original))

    def test_no_pipfile_returns_true_without_invoking(self):
        """No Pipfile -> nothing invoked, helper returns True (pipenv path untested)."""
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            self._patch_subprocess_run(lambda *a, **kw: calls.append((a, kw)))
            self.assertTrue(subtree._cleanup_pipenv_envs(tmp))
            self.assertEqual(calls, [])

    def test_invokes_pipenv_once_per_pipfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            sub = os.path.join(tmp, "service")
            os.mkdir(sub)
            with open(os.path.join(sub, "Pipfile"), "w") as f:
                f.write("")
            calls = []

            class FakeResult:
                returncode = 0

            def fake_run(cmd, **kwargs):
                calls.append((cmd, kwargs.get("cwd")))
                return FakeResult()

            self._patch_subprocess_run(fake_run)
            self.assertTrue(subtree._cleanup_pipenv_envs(tmp))
            self.assertEqual(len(calls), 1)
            cmd, cwd = calls[0]
            self.assertEqual(cmd[:2], ["pipenv", "--rm"])
            self.assertEqual(cwd, sub)

    def test_returns_false_when_pipenv_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "Pipfile"), "w") as f:
                f.write("")

            def fake_run(*args, **kwargs):
                raise FileNotFoundError("pipenv")

            self._patch_subprocess_run(fake_run)
            self.assertFalse(subtree._cleanup_pipenv_envs(tmp))


class TestCleanupComposeStacks(unittest.TestCase):
    """R060017 — docker compose down invocation; graceful skip when missing."""

    def _patch_subprocess_run(self, replacement):
        original = subtree.subprocess.run
        subtree.subprocess.run = replacement
        self.addCleanup(lambda: setattr(subtree.subprocess, "run", original))

    def test_no_compose_returns_true_without_invoking(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            self._patch_subprocess_run(lambda *a, **kw: calls.append((a, kw)))
            self.assertTrue(subtree._cleanup_compose_stacks(tmp))
            self.assertEqual(calls, [])

    def test_invokes_docker_compose_down_once_per_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            sub = os.path.join(tmp, "service")
            os.mkdir(sub)
            with open(os.path.join(sub, "compose.yaml"), "w") as f:
                f.write("")
            calls = []

            class FakeResult:
                returncode = 0

            def fake_run(cmd, **kwargs):
                calls.append((cmd, kwargs.get("cwd")))
                return FakeResult()

            self._patch_subprocess_run(fake_run)
            self.assertTrue(subtree._cleanup_compose_stacks(tmp))
            self.assertEqual(len(calls), 1)
            cmd, cwd = calls[0]
            self.assertEqual(cmd, ["docker", "compose", "down", "-v"])
            self.assertEqual(cwd, sub)

    def test_passes_volume_flag(self):
        """R060017: `down` runs with -v so named volumes are removed too."""
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "docker-compose.yml"), "w") as f:
                f.write("")
            captured = []

            class FakeResult:
                returncode = 0

            def fake_run(cmd, **kwargs):
                captured.append(cmd)
                return FakeResult()

            self._patch_subprocess_run(fake_run)
            subtree._cleanup_compose_stacks(tmp)
            self.assertIn("-v", captured[0])

    def test_returns_false_when_docker_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "docker-compose.yml"), "w") as f:
                f.write("")

            def fake_run(*args, **kwargs):
                raise FileNotFoundError("docker")

            self._patch_subprocess_run(fake_run)
            self.assertFalse(subtree._cleanup_compose_stacks(tmp))


class TestCleanupWorktree(unittest.TestCase):
    """R060012 / R060017 — combined result reports each tool independently."""

    def _patch_subprocess_run(self, replacement):
        original = subtree.subprocess.run
        subtree.subprocess.run = replacement
        self.addCleanup(lambda: setattr(subtree.subprocess, "run", original))

    def test_both_ran_when_nothing_to_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                subtree._cleanup_worktree(tmp),
                {"pipenv": True, "docker": True},
            )

    def test_missing_docker_does_not_skip_pipenv(self):
        """The two cleanups are independent (R060017)."""
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "Pipfile"), "w") as f:
                f.write("")
            with open(os.path.join(tmp, "docker-compose.yml"), "w") as f:
                f.write("")

            class FakeResult:
                returncode = 0

            def fake_run(cmd, **kwargs):
                if cmd and cmd[0] == "docker":
                    raise FileNotFoundError("docker")
                return FakeResult()

            self._patch_subprocess_run(fake_run)
            self.assertEqual(
                subtree._cleanup_worktree(tmp),
                {"pipenv": True, "docker": False},
            )

    def test_missing_pipenv_does_not_skip_docker(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "Pipfile"), "w") as f:
                f.write("")
            with open(os.path.join(tmp, "docker-compose.yml"), "w") as f:
                f.write("")

            class FakeResult:
                returncode = 0

            def fake_run(cmd, **kwargs):
                if cmd and cmd[0] == "pipenv":
                    raise FileNotFoundError("pipenv")
                return FakeResult()

            self._patch_subprocess_run(fake_run)
            self.assertEqual(
                subtree._cleanup_worktree(tmp),
                {"pipenv": False, "docker": True},
            )


class TestConfirmSafeRemoval(unittest.TestCase):
    """R060008 / R060009 / R060010 / R060011 routed through one function."""

    def _patch_dialog(self, return_value):
        captured = []

        def fake_dialog(msg, ok_title="OK"):
            captured.append(msg)
            return return_value

        import sublime
        original = sublime.ok_cancel_dialog
        sublime.ok_cancel_dialog = fake_dialog
        self.addCleanup(lambda: setattr(sublime, "ok_cancel_dialog", original))
        return captured

    def test_clean_and_in_sync_returns_ok_without_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            sha = subprocess.run(
                ["git", "-C", tmp, "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "-C", tmp, "remote", "add", "origin",
                 "https://example.invalid/x.git"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "update-ref", "refs/remotes/origin/master", sha],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "branch", "--set-upstream-to=origin/master", "master"],
                check=True, capture_output=True,
            )
            captured = self._patch_dialog(False)  # would fail if called
            ok, reason = subtree._confirm_safe_removal(tmp, "master")
            self.assertTrue(ok)
            self.assertIsNone(reason)
            self.assertEqual(captured, [])

    def test_uncommitted_blocks_without_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            with open(os.path.join(tmp, "extra.txt"), "w") as f:
                f.write("x")
            captured = self._patch_dialog(True)
            ok, reason = subtree._confirm_safe_removal(tmp, "master")
            self.assertFalse(ok)
            self.assertIn("uncommitted", reason.lower())
            self.assertEqual(captured, [])

    def test_no_upstream_no_unique_commits_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            subprocess.run(
                ["git", "-C", tmp, "checkout", "-q", "-b", "feature"],
                check=True, capture_output=True,
            )
            captured = self._patch_dialog(False)  # would fail if called
            ok, reason = subtree._confirm_safe_removal(tmp, "feature")
            self.assertTrue(ok)
            self.assertIsNone(reason)
            self.assertEqual(captured, [])

    def test_no_upstream_with_unique_commits_prompts_and_confirms(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            subprocess.run(
                ["git", "-C", tmp, "checkout", "-q", "-b", "feature"],
                check=True, capture_output=True,
            )
            with open(os.path.join(tmp, "extra.txt"), "w") as f:
                f.write("x")
            subprocess.run(
                ["git", "-C", tmp, "add", "extra.txt"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "commit", "-q", "-m", "extra"],
                check=True, capture_output=True,
            )
            captured = self._patch_dialog(True)
            ok, reason = subtree._confirm_safe_removal(tmp, "feature")
            self.assertTrue(ok)
            self.assertIsNone(reason)
            self.assertEqual(len(captured), 1)
            self.assertIn("no upstream", captured[0].lower())

    def test_no_upstream_with_unique_commits_user_cancels(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            subprocess.run(
                ["git", "-C", tmp, "checkout", "-q", "-b", "feature"],
                check=True, capture_output=True,
            )
            with open(os.path.join(tmp, "extra.txt"), "w") as f:
                f.write("x")
            subprocess.run(
                ["git", "-C", tmp, "add", "extra.txt"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "commit", "-q", "-m", "extra"],
                check=True, capture_output=True,
            )
            self._patch_dialog(False)
            ok, reason = subtree._confirm_safe_removal(tmp, "feature")
            self.assertFalse(ok)
            self.assertIn("upstream", reason.lower())

    def test_ahead_user_confirms(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            sha = subprocess.run(
                ["git", "-C", tmp, "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "-C", tmp, "remote", "add", "origin",
                 "https://example.invalid/x.git"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "update-ref", "refs/remotes/origin/master", sha],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "branch", "--set-upstream-to=origin/master", "master"],
                check=True, capture_output=True,
            )
            with open(os.path.join(tmp, "extra.txt"), "w") as f:
                f.write("x")
            subprocess.run(
                ["git", "-C", tmp, "add", "extra.txt"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "commit", "-q", "-m", "ahead"],
                check=True, capture_output=True,
            )
            captured = self._patch_dialog(True)
            ok, reason = subtree._confirm_safe_removal(tmp, "master")
            self.assertTrue(ok)
            self.assertIsNone(reason)
            self.assertEqual(len(captured), 1)
            self.assertIn("ahead", captured[0].lower())

    def test_ahead_user_cancels(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            sha = subprocess.run(
                ["git", "-C", tmp, "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "-C", tmp, "remote", "add", "origin",
                 "https://example.invalid/x.git"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "update-ref", "refs/remotes/origin/master", sha],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "branch", "--set-upstream-to=origin/master", "master"],
                check=True, capture_output=True,
            )
            with open(os.path.join(tmp, "extra.txt"), "w") as f:
                f.write("x")
            subprocess.run(
                ["git", "-C", tmp, "add", "extra.txt"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "commit", "-q", "-m", "ahead"],
                check=True, capture_output=True,
            )
            self._patch_dialog(False)
            ok, reason = subtree._confirm_safe_removal(tmp, "master")
            self.assertFalse(ok)
            self.assertIn("ahead", reason.lower())


class TestDoRemove(unittest.TestCase):
    """End-to-end orchestration."""

    def _read_config(self, root):
        with open(os.path.join(root, subtree.CONFIG_FILENAME)) as f:
            return json.load(f)

    def test_full_removal(self):
        """R060013 / R060014 / R060015: worktree gone, project deleted, config updated."""
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            wt, proj = _add_worktree(root, config, main_dir, "feature_a")
            self.assertTrue(os.path.isdir(wt))
            self.assertTrue(os.path.isfile(proj))

            entry = next(w for w in config["worktrees"] if w["name"] == "feature_a")
            cleanup = subtree._do_remove(root, config, entry, wt, main_dir)
            # no Pipfile / compose file -> nothing to invoke; both report True.
            self.assertEqual(cleanup, {"pipenv": True, "docker": True})
            self.assertFalse(os.path.isdir(wt))
            self.assertFalse(os.path.isfile(proj))

            new_config = self._read_config(root)
            self.assertEqual(
                [w["name"] for w in new_config["worktrees"]],
                ["master"],
            )

            # git no longer lists the worktree.
            wt_list = subprocess.run(
                ["git", "-C", main_dir, "worktree", "list", "--porcelain"],
                check=True, capture_output=True, text=True,
            ).stdout
            self.assertNotIn("feature_a", wt_list)

    def test_cleanup_skipped_when_pipenv_missing(self):
        """R060012: pipenv not on PATH -> _do_remove reports pipenv skipped; everything else still runs."""
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            wt, proj = _add_worktree(root, config, main_dir, "feature_b")
            # Drop a Pipfile so the cleanup path is exercised.
            with open(os.path.join(wt, "Pipfile"), "w") as f:
                f.write("")
            subprocess.run(
                ["git", "-C", wt, "add", "Pipfile"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", wt, "commit", "-q", "-m", "add pipfile"],
                check=True, capture_output=True,
            )

            original = subtree.subprocess.run

            def fake_run(cmd, **kwargs):
                if cmd and cmd[0] == "pipenv":
                    raise FileNotFoundError("pipenv")
                return original(cmd, **kwargs)

            subtree.subprocess.run = fake_run
            try:
                entry = next(w for w in config["worktrees"] if w["name"] == "feature_b")
                cleanup = subtree._do_remove(root, config, entry, wt, main_dir)
            finally:
                subtree.subprocess.run = original

            self.assertFalse(cleanup["pipenv"])
            self.assertTrue(cleanup["docker"])  # no compose file -> docker cleanup is a no-op
            self.assertFalse(os.path.isdir(wt))
            self.assertFalse(os.path.isfile(proj))
            new_config = self._read_config(root)
            self.assertEqual(
                [w["name"] for w in new_config["worktrees"]],
                ["master"],
            )


if __name__ == "__main__":
    unittest.main()
