"""Tests for the Subtree `prune` operation.

Each test references the relevant R-codes from `docs/requirements.md` so
the link between behaviour and the authoritative spec is explicit
(per the doc-first rule in CLAUDE.md).
"""

import json
import os
import shutil
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


def _read_config(root):
    with open(os.path.join(root, subtree.CONFIG_FILENAME)) as f:
        return json.load(f)


class TestFindStaleWorktrees(unittest.TestCase):
    """R080005 — stale = entry whose worktree dir is missing, minus the main worktree."""

    def test_all_present_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            _add_worktree(root, config, main_dir, "feature_a")
            self.assertEqual(subtree._find_stale_worktrees(root, config), [])

    def test_missing_directory_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            wt, _proj = _add_worktree(root, config, main_dir, "feature_a")
            _add_worktree(root, config, main_dir, "feature_b")
            # Delete feature_a's directory outside Subtree.
            shutil.rmtree(wt)
            stale = subtree._find_stale_worktrees(root, config)
            self.assertEqual([e["name"] for e in stale], ["feature_a"])

    def test_main_worktree_never_stale(self):
        """R010001 — the main worktree is excluded even if its dir is missing."""
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            shutil.rmtree(main_dir)  # pathological, but must never be flagged
            self.assertEqual(subtree._find_stale_worktrees(root, config), [])

    def test_multiple_stale_in_config_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            wt_a, _ = _add_worktree(root, config, main_dir, "feature_a")
            _add_worktree(root, config, main_dir, "feature_b")
            wt_c, _ = _add_worktree(root, config, main_dir, "feature_c")
            shutil.rmtree(wt_a)
            shutil.rmtree(wt_c)
            stale = subtree._find_stale_worktrees(root, config)
            self.assertEqual([e["name"] for e in stale], ["feature_a", "feature_c"])


class TestDoPrune(unittest.TestCase):
    """R080007 / R080008 / R080010 — file cleanup, config rewrite, warnings."""

    def test_deletes_project_and_workspace_and_drops_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            wt, proj = _add_worktree(root, config, main_dir, "feature_a")
            # A user session leaves a .sublime-workspace next to the project.
            workspace = proj.replace(".sublime-project", ".sublime-workspace")
            with open(workspace, "w") as f:
                f.write("{}")
            shutil.rmtree(wt)

            stale = subtree._find_stale_worktrees(root, config)
            results, warnings = subtree._do_prune(root, config, stale)

            self.assertEqual(warnings, [])
            self.assertEqual([r["name"] for r in results], ["feature_a"])
            self.assertEqual(sorted(results[0]["removed_files"]), sorted([proj, workspace]))
            self.assertFalse(os.path.isfile(proj))
            self.assertFalse(os.path.isfile(workspace))

            new_config = _read_config(root)
            self.assertEqual([w["name"] for w in new_config["worktrees"]], ["master"])

    def test_missing_workspace_only_removes_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            wt, proj = _add_worktree(root, config, main_dir, "feature_a")
            shutil.rmtree(wt)

            stale = subtree._find_stale_worktrees(root, config)
            results, warnings = subtree._do_prune(root, config, stale)

            self.assertEqual(warnings, [])
            self.assertEqual(results[0]["removed_files"], [proj])
            self.assertFalse(os.path.isfile(proj))

    def test_preserves_other_worktrees_and_config_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            wt_a, _ = _add_worktree(root, config, main_dir, "feature_a")
            _add_worktree(root, config, main_dir, "feature_b")
            # Give settings a value to confirm it survives the rewrite.
            config["settings"]["copy_directories"] = [".venv"]
            shutil.rmtree(wt_a)

            stale = subtree._find_stale_worktrees(root, config)
            subtree._do_prune(root, config, stale)

            new_config = _read_config(root)
            self.assertEqual(
                sorted(w["name"] for w in new_config["worktrees"]),
                ["feature_b", "master"],
            )
            self.assertEqual(new_config["settings"]["copy_directories"], [".venv"])
            self.assertEqual(new_config["meta_information"]["main_worktree"], "master")

    def test_config_rewrite_format_matches(self):
        """R080008 — 4-space indent + trailing newline, like every other rewrite."""
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            wt, _ = _add_worktree(root, config, main_dir, "feature_a")
            shutil.rmtree(wt)
            subtree._do_prune(root, config, subtree._find_stale_worktrees(root, config))
            with open(os.path.join(root, subtree.CONFIG_FILENAME)) as f:
                text = f.read()
            self.assertTrue(text.endswith("}\n"))
            self.assertIn('\n    "worktrees"', text)

    def test_file_deletion_failure_warns_but_drops_entry(self):
        """R080010 — a failed delete is a warning, not an abort; entry still removed."""
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            wt, proj = _add_worktree(root, config, main_dir, "feature_a")
            shutil.rmtree(wt)

            original_remove = subtree.os.remove

            def fake_remove(path):
                if path == proj:
                    raise OSError("permission denied")
                return original_remove(path)

            subtree.os.remove = fake_remove
            try:
                stale = subtree._find_stale_worktrees(root, config)
                results, warnings = subtree._do_prune(root, config, stale)
            finally:
                subtree.os.remove = original_remove

            self.assertEqual(len(warnings), 1)
            self.assertIn(proj, warnings[0])
            self.assertEqual(results[0]["removed_files"], [])  # nothing deleted
            # Entry is still dropped from config despite the failed delete.
            new_config = _read_config(root)
            self.assertEqual([w["name"] for w in new_config["worktrees"]], ["master"])


class TestFindOrphanFiles(unittest.TestCase):
    """R080011 — orphan = project/workspace file in sublime_projects/ that no
    `worktrees[]` entry references."""

    def _projects_dir(self, root):
        return os.path.join(root, subtree.SUBLIME_PROJECTS_DIRNAME)

    def test_no_orphans_when_everything_referenced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            _, proj = _add_worktree(root, config, main_dir, "feature_a")
            # A workspace next to a referenced project is itself referenced.
            with open(proj.replace(".sublime-project", ".sublime-workspace"), "w") as f:
                f.write("{}")
            self.assertEqual(subtree._find_orphan_files(root, config), [])

    def test_unreferenced_project_and_workspace_are_orphans(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            projects = self._projects_dir(root)
            orphan_proj = os.path.join(projects, "my_app_gone.sublime-project")
            orphan_ws = os.path.join(projects, "my_app_gone.sublime-workspace")
            with open(orphan_proj, "w") as f:
                f.write("{}")
            with open(orphan_ws, "w") as f:
                f.write("{}")
            self.assertEqual(
                subtree._find_orphan_files(root, config),
                sorted([orphan_proj, orphan_ws]),
            )

    def test_main_worktree_files_never_orphaned(self):
        """R010001 — the main worktree entry always references its files."""
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            main_proj = os.path.join(
                self._projects_dir(root), "my_app_master.sublime-project"
            )
            with open(main_proj.replace(".sublime-project", ".sublime-workspace"), "w") as f:
                f.write("{}")
            self.assertEqual(subtree._find_orphan_files(root, config), [])

    def test_stale_entry_files_are_not_orphans(self):
        """R080011 — files of a still-present (stale) entry are referenced, so the
        stale-entry path (R080007), not the orphan path, handles them."""
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            wt, _proj = _add_worktree(root, config, main_dir, "feature_a")
            shutil.rmtree(wt)  # entry is now stale, but still in config
            self.assertEqual(subtree._find_orphan_files(root, config), [])

    def test_unrelated_files_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            keep = os.path.join(self._projects_dir(root), "README.txt")
            with open(keep, "w") as f:
                f.write("not ours\n")
            self.assertEqual(subtree._find_orphan_files(root, config), [])
            self.assertTrue(os.path.isfile(keep))


class TestDeleteOrphanFiles(unittest.TestCase):
    """R080012 — delete orphaned files; failures warn but do not abort."""

    def test_deletes_and_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            projects = os.path.join(root, subtree.SUBLIME_PROJECTS_DIRNAME)
            orphan = os.path.join(projects, "my_app_gone.sublime-project")
            with open(orphan, "w") as f:
                f.write("{}")
            removed, warnings = subtree._delete_orphan_files([orphan])
            self.assertEqual(removed, [orphan])
            self.assertEqual(warnings, [])
            self.assertFalse(os.path.isfile(orphan))

    def test_failure_warns_but_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            projects = os.path.join(root, subtree.SUBLIME_PROJECTS_DIRNAME)
            bad = os.path.join(projects, "my_app_bad.sublime-project")
            good = os.path.join(projects, "my_app_good.sublime-workspace")
            for p in (bad, good):
                with open(p, "w") as f:
                    f.write("{}")

            original_remove = subtree.os.remove

            def fake_remove(path):
                if path == bad:
                    raise OSError("permission denied")
                return original_remove(path)

            subtree.os.remove = fake_remove
            try:
                removed, warnings = subtree._delete_orphan_files([bad, good])
            finally:
                subtree.os.remove = original_remove

            self.assertEqual(removed, [good])
            self.assertEqual(len(warnings), 1)
            self.assertIn(bad, warnings[0])
            self.assertFalse(os.path.isfile(good))
            self.assertTrue(os.path.isfile(bad))


if __name__ == "__main__":
    unittest.main()
