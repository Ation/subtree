"""Tests for the Subtree `open` operation and the cross-cutting changes
(R010002 / R010003 / R030010 relaxations) introduced alongside it.

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
    """Init a git repo, then run `_do_init`. Returns (root, config, main_dir)."""
    _init_git_repo(tmp, initial_branch=branch)
    subtree._do_init(tmp, repo_name, branch)
    with open(os.path.join(tmp, subtree.CONFIG_FILENAME)) as f:
        config = json.load(f)
    main_dir = os.path.join(tmp, subtree.WORKTREES_DIRNAME, branch)
    return tmp, config, main_dir


class TestValidateBranchNameRelaxed(unittest.TestCase):
    """R030010 (rewritten): '/' allowed, '\\' / ctrl / bad segments rejected."""

    def test_accepts_plain_identifier(self):
        self.assertIsNone(subtree._validate_branch_name("feature_1"))

    def test_accepts_branch_with_slash(self):
        self.assertIsNone(subtree._validate_branch_name("feature/foo"))
        self.assertIsNone(subtree._validate_branch_name("a/b/c"))

    def test_rejects_empty(self):
        self.assertIsNotNone(subtree._validate_branch_name(""))

    def test_rejects_backslash(self):
        self.assertIsNotNone(subtree._validate_branch_name("foo\\bar"))

    def test_rejects_control_char(self):
        self.assertIsNotNone(subtree._validate_branch_name("foo\nbar"))
        self.assertIsNotNone(subtree._validate_branch_name("foo\x00bar"))

    def test_rejects_leading_slash(self):
        self.assertIsNotNone(subtree._validate_branch_name("/foo"))

    def test_rejects_trailing_slash(self):
        self.assertIsNotNone(subtree._validate_branch_name("foo/"))

    def test_rejects_doubled_slash(self):
        self.assertIsNotNone(subtree._validate_branch_name("foo//bar"))

    def test_rejects_dot_segment(self):
        self.assertIsNotNone(subtree._validate_branch_name("foo/./bar"))

    def test_rejects_dotdot_segment(self):
        self.assertIsNotNone(subtree._validate_branch_name("foo/../bar"))


class TestBranchToProjectFilename(unittest.TestCase):
    """R010003: '/' in branch name -> '__' in the filename component."""

    def test_plain_branch(self):
        self.assertEqual(
            subtree._branch_to_project_filename("my_app", "master"),
            "my_app_master.sublime-project",
        )

    def test_single_slash(self):
        self.assertEqual(
            subtree._branch_to_project_filename("my_app", "feature/foo"),
            "my_app_feature__foo.sublime-project",
        )

    def test_multi_slash(self):
        self.assertEqual(
            subtree._branch_to_project_filename("my_app", "a/b/c"),
            "my_app_a__b__c.sublime-project",
        )


class TestListOpenableBranches(unittest.TestCase):
    """R040005 / R040006: enumerate refs/heads + refs/remotes, skip symrefs."""

    def test_returns_local_branches(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp, initial_branch="master")
            subprocess.run(
                ["git", "-C", tmp, "branch", "feature_x"],
                check=True, capture_output=True,
            )
            cands = subtree._list_openable_branches(tmp)
            names = {(c["local_name"], c["remote"]) for c in cands}
            self.assertIn(("master", None), names)
            self.assertIn(("feature_x", None), names)

    def test_returns_remote_branches_with_prefix_stripped(self):
        """Remote ref appears with local_name = stripped, remote = 'origin'."""
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp, initial_branch="master")
            sha = subprocess.run(
                ["git", "-C", tmp, "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            # Fabricate a remote-tracking ref pointing at master's commit.
            subprocess.run(
                ["git", "-C", tmp, "update-ref", "refs/remotes/origin/feature_r", sha],
                check=True, capture_output=True,
            )
            cands = subtree._list_openable_branches(tmp)
            remote = next(c for c in cands if c["remote"] == "origin")
            self.assertEqual(remote["local_name"], "feature_r")
            self.assertEqual(remote["ref"], "origin/feature_r")
            self.assertIn("(origin)", remote["display"])

    def test_strips_only_first_path_component_for_remote(self):
        """For `origin/feature/foo`, local_name == `feature/foo`."""
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp, initial_branch="master")
            sha = subprocess.run(
                ["git", "-C", tmp, "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "-C", tmp, "update-ref", "refs/remotes/origin/feature/foo", sha],
                check=True, capture_output=True,
            )
            cands = subtree._list_openable_branches(tmp)
            remote = next(c for c in cands if c["remote"] == "origin")
            self.assertEqual(remote["local_name"], "feature/foo")

    def test_skips_symref_head_pointers(self):
        """`refs/remotes/origin/HEAD` is symbolic and must be excluded."""
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp, initial_branch="master")
            sha = subprocess.run(
                ["git", "-C", tmp, "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "-C", tmp, "update-ref", "refs/remotes/origin/master", sha],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", tmp, "symbolic-ref",
                 "refs/remotes/origin/HEAD", "refs/remotes/origin/master"],
                check=True, capture_output=True,
            )
            cands = subtree._list_openable_branches(tmp)
            # No candidate's local_name should be 'HEAD'.
            self.assertNotIn("HEAD", [c["local_name"] for c in cands])


class TestFilterOpenable(unittest.TestCase):
    """R040007: filter already-managed locals and remote duplicates of locals."""

    def _c_local(self, name):
        return {"display": name, "local_name": name, "remote": None, "ref": name}

    def _c_remote(self, name, remote="origin"):
        return {
            "display": "{}  ({})".format(name, remote),
            "local_name": name,
            "remote": remote,
            "ref": "{}/{}".format(remote, name),
        }

    def test_drops_local_with_existing_worktree(self):
        candidates = [self._c_local("master"), self._c_local("feature_x")]
        result = subtree._filter_openable(candidates, {"master"}, {"master", "feature_x"})
        self.assertEqual([c["local_name"] for c in result], ["feature_x"])

    def test_drops_remote_with_existing_worktree(self):
        candidates = [self._c_remote("master"), self._c_remote("feature_y")]
        result = subtree._filter_openable(candidates, {"master"}, set())
        self.assertEqual([c["local_name"] for c in result], ["feature_y"])

    def test_drops_remote_whose_local_form_exists(self):
        """If `feature_a` is already a local branch, hide `origin/feature_a`."""
        candidates = [self._c_local("feature_a"), self._c_remote("feature_a")]
        result = subtree._filter_openable(candidates, set(), {"feature_a"})
        self.assertEqual(
            [(c["local_name"], c["remote"]) for c in result],
            [("feature_a", None)],
        )

    def test_keeps_remote_when_no_local(self):
        candidates = [self._c_remote("only_remote")]
        result = subtree._filter_openable(candidates, set(), set())
        self.assertEqual([c["local_name"] for c in result], ["only_remote"])


class TestDoOpenViaDoCreate(unittest.TestCase):
    """End-to-end open flows reuse `_do_create`; this exercises both paths."""

    def _read_config(self, root):
        with open(os.path.join(root, subtree.CONFIG_FILENAME)) as f:
            return json.load(f)

    def _open(self, root, config, main_dir, candidate, template_name="master"):
        """Wrap the orchestration the WindowCommand normally does, but synchronously."""
        repo_name = config["meta_information"]["repository_name"]
        branch = candidate["local_name"]
        new_worktree_dir = os.path.join(root, subtree.WORKTREES_DIRNAME, branch)
        project_filename = subtree._branch_to_project_filename(repo_name, branch)
        new_project_path = os.path.join(
            root, subtree.SUBLIME_PROJECTS_DIRNAME, project_filename
        )
        # Template source = main worktree's project file (by default).
        template_entry = next(wt for wt in config["worktrees"] if wt["name"] == template_name)
        template_path = os.path.join(
            root, subtree.SUBLIME_PROJECTS_DIRNAME, template_entry["project_file"]
        )
        source_template = subtree._load_source_template(template_path)
        base_branch = None if candidate["remote"] is None else candidate["ref"]
        subtree._do_create(
            main_dir, template_name, source_template,
            new_worktree_dir, new_project_path,
            branch, base_branch, project_filename, root, config,
        )
        return new_worktree_dir, new_project_path

    def test_opens_local_branch_without_worktree(self):
        """R040015: existing local branch → check it out, no new branch object."""
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            subprocess.run(
                ["git", "-C", main_dir, "branch", "feature_loc"],
                check=True, capture_output=True,
            )
            before = subprocess.run(
                ["git", "-C", main_dir, "for-each-ref", "refs/heads/"],
                check=True, capture_output=True, text=True,
            ).stdout

            candidate = {
                "display": "feature_loc", "local_name": "feature_loc",
                "remote": None, "ref": "feature_loc",
            }
            wt, _ = self._open(root, config, main_dir, candidate)

            after = subprocess.run(
                ["git", "-C", main_dir, "for-each-ref", "refs/heads/"],
                check=True, capture_output=True, text=True,
            ).stdout
            self.assertEqual(before, after)  # No new branch object created.
            current = subprocess.run(
                ["git", "-C", wt, "branch", "--show-current"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            self.assertEqual(current, "feature_loc")
            new_config = self._read_config(root)
            self.assertEqual(new_config["worktrees"][-1]["created_from"], "master")

    def test_opens_remote_branch_with_prefix_stripped(self):
        """R040016: remote-only → new tracking local branch."""
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            # Configure 'origin' as a real remote so auto-tracking works the
            # way it does in production (git only sets upstream when the
            # remote is known in .git/config). The URL need not be reachable.
            subprocess.run(
                ["git", "-C", main_dir, "remote", "add", "origin",
                 "https://example.invalid/fake.git"],
                check=True, capture_output=True,
            )
            sha = subprocess.run(
                ["git", "-C", main_dir, "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "-C", main_dir, "update-ref",
                 "refs/remotes/origin/feature_rem", sha],
                check=True, capture_output=True,
            )

            candidate = {
                "display": "feature_rem  (origin)",
                "local_name": "feature_rem",
                "remote": "origin",
                "ref": "origin/feature_rem",
            }
            wt, _ = self._open(root, config, main_dir, candidate)

            current = subprocess.run(
                ["git", "-C", wt, "branch", "--show-current"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            self.assertEqual(current, "feature_rem")  # local name only, no 'origin/'
            # Tracking should be set up.
            upstream = subprocess.run(
                ["git", "-C", wt, "for-each-ref",
                 "--format=%(upstream:short)", "refs/heads/feature_rem"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            self.assertEqual(upstream, "origin/feature_rem")

    def test_opens_branch_with_slash_creates_nested_worktree(self):
        """R010002 / R010003: branch `feature/foo` → nested worktree + flat project."""
        with tempfile.TemporaryDirectory() as tmp:
            root, config, main_dir = _make_subtree_repo(tmp)
            subprocess.run(
                ["git", "-C", main_dir, "branch", "feature/foo"],
                check=True, capture_output=True,
            )

            candidate = {
                "display": "feature/foo", "local_name": "feature/foo",
                "remote": None, "ref": "feature/foo",
            }
            wt, proj = self._open(root, config, main_dir, candidate)

            # Worktree dir is nested.
            self.assertEqual(
                wt, os.path.join(root, "worktrees", "feature", "foo"),
            )
            self.assertTrue(os.path.isdir(wt))

            # Project file is flat with '__' substitution (R010003).
            self.assertEqual(
                proj,
                os.path.join(root, "sublime_projects", "my_app_feature__foo.sublime-project"),
            )
            self.assertTrue(os.path.isfile(proj))

            # Config entry preserves the slash in `name`.
            new_config = self._read_config(root)
            entry = new_config["worktrees"][-1]
            self.assertEqual(entry["name"], "feature/foo")
            self.assertEqual(entry["project_file"], "my_app_feature__foo.sublime-project")


class TestOpenCopiesDirectoriesFromTemplate(unittest.TestCase):
    """R040021 — open copies directories from the template-source worktree.

    The git base is the main worktree (R040015 / R040016), but `copy_directories`
    must read from the template-source picked in R040013 — this test proves the
    two are distinguished by setting up the gitignored content only on the
    template worktree and confirming it lands in the newly opened one.
    """

    def _set_copy_directories(self, root, entries):
        path = os.path.join(root, subtree.CONFIG_FILENAME)
        with open(path) as f:
            data = json.load(f)
        data["settings"] = {"copy_directories": entries}
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
            f.write("\n")
        with open(path) as f:
            return json.load(f)

    def _make_template_worktree(self, root, main_dir, template_name):
        """Use `_do_create` to materialise a non-main worktree that will serve
        as the open-template source. Returns the new worktree directory.
        """
        subprocess.run(
            ["git", "-C", main_dir, "branch", template_name],
            check=True, capture_output=True,
        )
        with open(os.path.join(root, subtree.CONFIG_FILENAME)) as f:
            config = json.load(f)
        repo_name = config["meta_information"]["repository_name"]
        new_wt = os.path.join(root, subtree.WORKTREES_DIRNAME, template_name)
        project_filename = subtree._branch_to_project_filename(repo_name, template_name)
        new_project_path = os.path.join(
            root, subtree.SUBLIME_PROJECTS_DIRNAME, project_filename
        )
        source_template = subtree._load_source_template(os.path.join(
            root, subtree.SUBLIME_PROJECTS_DIRNAME, "my_app_master.sublime-project"
        ))
        subtree._do_create(
            main_dir, "master", source_template,
            new_wt, new_project_path,
            template_name, None, project_filename, root, config,
        )
        return new_wt

    def test_open_copies_from_template_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _, main_dir = _make_subtree_repo(tmp)

            # Bring a non-main template worktree online and add a gitignored
            # .venv to it only (the main worktree gets none).
            template_dir = self._make_template_worktree(root, main_dir, "template_wt")
            with open(os.path.join(template_dir, ".gitignore"), "w") as f:
                f.write(".venv/\n")
            subprocess.run(
                ["git", "-C", template_dir, "add", ".gitignore"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", template_dir, "commit", "-q", "-m", "ignore"],
                check=True, capture_output=True,
            )
            os.makedirs(os.path.join(template_dir, ".venv"))
            with open(os.path.join(template_dir, ".venv", "marker.txt"), "w") as f:
                f.write("from-template")

            # Configure the copy list and create a target branch to open.
            config = self._set_copy_directories(root, [".venv"])
            subprocess.run(
                ["git", "-C", main_dir, "branch", "to_open"],
                check=True, capture_output=True,
            )

            # Mirror `_run_open`: git base is `main_dir`, copy source is the
            # template worktree.
            repo_name = config["meta_information"]["repository_name"]
            new_wt = os.path.join(root, subtree.WORKTREES_DIRNAME, "to_open")
            project_filename = subtree._branch_to_project_filename(repo_name, "to_open")
            new_project_path = os.path.join(
                root, subtree.SUBLIME_PROJECTS_DIRNAME, project_filename
            )
            source_template = subtree._load_source_template(os.path.join(
                root, subtree.SUBLIME_PROJECTS_DIRNAME,
                "my_app_template_wt.sublime-project",
            ))
            subtree._do_create(
                main_dir, "template_wt", source_template,
                new_wt, new_project_path,
                "to_open", None, project_filename, root, config,
            )
            warnings = subtree._copy_listed_directories(
                template_dir, new_wt, subtree._get_copy_directories(config),
            )

            self.assertEqual(warnings, [])
            with open(os.path.join(new_wt, ".venv", "marker.txt")) as f:
                self.assertEqual(f.read(), "from-template")


if __name__ == "__main__":
    unittest.main()
