"""Tests for the Subtree `create` operation.

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
    """Build a fully-init-ed Subtree repo at `tmp`. Returns (root, config)."""
    _init_git_repo(tmp, initial_branch=branch)
    subtree._do_init(tmp, repo_name, branch)
    with open(os.path.join(tmp, subtree.CONFIG_FILENAME)) as f:
        config = json.load(f)
    return tmp, config


class TestValidateBranchName(unittest.TestCase):
    """R030010 — branch name must be non-empty and free of /, \\, ctrl chars."""

    def test_rejects_empty(self):
        self.assertIsNotNone(subtree._validate_branch_name(""))

    def test_rejects_backslash(self):
        self.assertIsNotNone(subtree._validate_branch_name("feature\\foo"))

    def test_rejects_control_char(self):
        self.assertIsNotNone(subtree._validate_branch_name("foo\nbar"))
        self.assertIsNotNone(subtree._validate_branch_name("foo\x00bar"))

    def test_accepts_plain_identifier(self):
        self.assertIsNone(subtree._validate_branch_name("feature_1"))
        self.assertIsNone(subtree._validate_branch_name("my-branch.v2"))


class TestFindRoot(unittest.TestCase):
    """R030002 / R030003 — walk upward looking for subtree_config.json."""

    def test_finds_root_at_start_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, subtree.CONFIG_FILENAME), "w") as f:
                f.write("{}")
            self.assertEqual(subtree._find_root(tmp), os.path.abspath(tmp))

    def test_finds_root_one_level_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, subtree.CONFIG_FILENAME), "w") as f:
                f.write("{}")
            sub = os.path.join(tmp, "sub")
            os.mkdir(sub)
            self.assertEqual(subtree._find_root(sub), os.path.abspath(tmp))

    def test_finds_root_from_worktree_subdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = _make_subtree_repo(tmp)
            worktree = os.path.join(root, "worktrees", "master")
            self.assertEqual(subtree._find_root(worktree), os.path.abspath(root))

    def test_returns_none_when_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(subtree._find_root(tmp))


class TestReadConfig(unittest.TestCase):
    """R030004 — read and structurally validate subtree_config.json."""

    def _write(self, root, content):
        with open(os.path.join(root, subtree.CONFIG_FILENAME), "w") as f:
            f.write(content)

    def test_returns_parsed_dict_for_valid_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_subtree_repo(tmp)
            data = subtree._read_config(tmp)
            self.assertEqual(data["meta_information"]["repository_name"], "my_app")

    def test_raises_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "{not json")
            with self.assertRaises(ValueError):
                subtree._read_config(tmp)

    def test_raises_when_meta_information_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, json.dumps({"worktrees": []}))
            with self.assertRaises(ValueError):
                subtree._read_config(tmp)

    def test_raises_when_worktrees_not_a_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, json.dumps({
                "meta_information": {"repository_name": "x", "main_worktree": "y"},
                "worktrees": {},
            }))
            with self.assertRaises(ValueError):
                subtree._read_config(tmp)

    def test_raises_when_worktree_entry_missing_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, json.dumps({
                "meta_information": {"repository_name": "x", "main_worktree": "y"},
                "worktrees": [{"name": "y"}],  # missing created_from + project_file
            }))
            with self.assertRaises(ValueError):
                subtree._read_config(tmp)


class TestLocalBranchExists(unittest.TestCase):
    """R030014 — detect whether a branch resolves locally."""

    def test_returns_true_for_default_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp, initial_branch="main")
            self.assertTrue(subtree._local_branch_exists(tmp, "main"))

    def test_returns_false_for_unknown_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            self.assertFalse(subtree._local_branch_exists(tmp, "does_not_exist"))

    def test_returns_true_for_freshly_created_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            subprocess.run(
                ["git", "-C", tmp, "branch", "feature_x"],
                check=True, capture_output=True,
            )
            self.assertTrue(subtree._local_branch_exists(tmp, "feature_x"))


class TestLoadSourceTemplate(unittest.TestCase):
    """R030008 — single-folder source templates only."""

    def _write(self, path, data):
        with open(path, "w") as f:
            if isinstance(data, str):
                f.write(data)
            else:
                json.dump(data, f)

    def test_returns_data_for_single_folder_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "x.sublime-project")
            self._write(p, {"folders": [{"path": "/some/path"}]})
            data = subtree._load_source_template(p)
            self.assertEqual(data["folders"][0]["path"], "/some/path")

    def test_raises_on_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                subtree._load_source_template(os.path.join(tmp, "missing.sublime-project"))

    def test_raises_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "x.sublime-project")
            self._write(p, "{not json")
            with self.assertRaises(ValueError):
                subtree._load_source_template(p)

    def test_raises_when_folders_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "x.sublime-project")
            self._write(p, {"settings": {}})
            with self.assertRaises(ValueError):
                subtree._load_source_template(p)

    def test_raises_when_folders_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "x.sublime-project")
            self._write(p, {"folders": []})
            with self.assertRaises(ValueError):
                subtree._load_source_template(p)

    def test_raises_when_folders_has_two_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "x.sublime-project")
            self._write(p, {"folders": [{"path": "/a"}, {"path": "/b"}]})
            with self.assertRaises(ValueError):
                subtree._load_source_template(p)


class TestRewriteTemplate(unittest.TestCase):
    """R030017 — recursive find/replace of the source worktree path."""

    def test_rewrites_folder_path(self):
        source = {"folders": [{"path": "/old"}]}
        new = subtree._rewrite_template(source, "/old", "/new")
        self.assertEqual(new["folders"][0]["path"], "/new")

    def test_preserves_other_top_level_keys(self):
        source = {
            "folders": [{"path": "/old"}],
            "settings": {"tab_size": 2},
            "build_systems": [{"name": "x"}],
        }
        new = subtree._rewrite_template(source, "/old", "/new")
        self.assertEqual(new["settings"], {"tab_size": 2})
        self.assertEqual(new["build_systems"], [{"name": "x"}])

    def test_preserves_extra_keys_inside_folders_entry(self):
        source = {"folders": [{
            "path": "/old",
            "folder_exclude_patterns": [".venv"],
            "name": "main",
        }]}
        new = subtree._rewrite_template(source, "/old", "/new")
        self.assertEqual(new["folders"][0]["folder_exclude_patterns"], [".venv"])
        self.assertEqual(new["folders"][0]["name"], "main")

    def test_does_not_mutate_source(self):
        source = {"folders": [{"path": "/old"}]}
        subtree._rewrite_template(source, "/old", "/new")
        self.assertEqual(source["folders"][0]["path"], "/old")

    def test_rewrites_path_in_build_systems_working_dir(self):
        source = {
            "folders": [{"path": "/repo/worktrees/master"}],
            "build_systems": [{"working_dir": "/repo/worktrees/master/src"}],
        }
        new = subtree._rewrite_template(
            source, "/repo/worktrees/master", "/repo/worktrees/feature/foo"
        )
        self.assertEqual(
            new["build_systems"][0]["working_dir"],
            "/repo/worktrees/feature/foo/src",
        )

    def test_rewrites_path_in_cmd_list_elements(self):
        source = {
            "folders": [{"path": "/repo/worktrees/master"}],
            "build_systems": [{"cmd": [
                "python",
                "/repo/worktrees/master/scripts/run.py",
                "--config",
                "/etc/app/config.yaml",
            ]}],
        }
        new = subtree._rewrite_template(
            source, "/repo/worktrees/master", "/repo/worktrees/feature/foo"
        )
        self.assertEqual(new["build_systems"][0]["cmd"], [
            "python",
            "/repo/worktrees/feature/foo/scripts/run.py",
            "--config",
            "/etc/app/config.yaml",
        ])

    def test_rewrites_deep_file_path_under_source(self):
        source = {
            "folders": [{"path": "/repo/worktrees/master"}],
            "settings": {"log_file": "/repo/worktrees/master/logs/sub/app.log"},
        }
        new = subtree._rewrite_template(
            source, "/repo/worktrees/master", "/repo/worktrees/feature/foo"
        )
        self.assertEqual(
            new["settings"]["log_file"],
            "/repo/worktrees/feature/foo/logs/sub/app.log",
        )

    def test_rewrites_path_inside_nested_settings_dict(self):
        source = {
            "folders": [{"path": "/old"}],
            "settings": {
                "nested": {
                    "deeper": {"path": "/old/a/b/c"},
                    "list": ["/old/x", "irrelevant"],
                }
            },
        }
        new = subtree._rewrite_template(source, "/old", "/new")
        self.assertEqual(new["settings"]["nested"]["deeper"]["path"], "/new/a/b/c")
        self.assertEqual(new["settings"]["nested"]["list"], ["/new/x", "irrelevant"])

    def test_ignores_relative_paths(self):
        source = {
            "folders": [{
                "path": "/repo/worktrees/master",
                "folder_exclude_patterns": [".venv", "build"],
            }],
            "settings": {"lint_dirs": ["src", "./scripts", "../sibling"]},
        }
        new = subtree._rewrite_template(
            source, "/repo/worktrees/master", "/repo/worktrees/feature/foo"
        )
        self.assertEqual(
            new["folders"][0]["folder_exclude_patterns"], [".venv", "build"]
        )
        self.assertEqual(
            new["settings"]["lint_dirs"], ["src", "./scripts", "../sibling"]
        )

    def test_ignores_absolute_paths_outside_source(self):
        source = {
            "folders": [{"path": "/repo/worktrees/master"}],
            "settings": {"external_tool": "/usr/local/bin/tool"},
        }
        new = subtree._rewrite_template(
            source, "/repo/worktrees/master", "/repo/worktrees/feature/foo"
        )
        self.assertEqual(
            new["settings"]["external_tool"], "/usr/local/bin/tool"
        )

    def test_does_not_rewrite_json_keys(self):
        source = {
            "folders": [{"path": "/old"}],
            "settings": {"/old": "value-stays"},
        }
        new = subtree._rewrite_template(source, "/old", "/new")
        self.assertIn("/old", new["settings"])
        self.assertNotIn("/new", new["settings"])
        self.assertEqual(new["settings"]["/old"], "value-stays")

    def test_naive_substring_swap_affects_sibling_paths(self):
        """Documented trade-off: literal str.replace rewrites sibling prefixes too."""
        source = {
            "folders": [{"path": "/repo/worktrees/master"}],
            "settings": {"sibling": "/repo/worktrees/master_old/x"},
        }
        new = subtree._rewrite_template(
            source, "/repo/worktrees/master", "/repo/worktrees/feature/foo"
        )
        self.assertEqual(
            new["settings"]["sibling"], "/repo/worktrees/feature/foo_old/x"
        )

    def test_passes_through_non_string_scalars(self):
        source = {
            "folders": [{"path": "/old"}],
            "settings": {"tab_size": 2, "translate_tabs_to_spaces": True, "ruler": None},
        }
        new = subtree._rewrite_template(source, "/old", "/new")
        self.assertEqual(new["settings"]["tab_size"], 2)
        self.assertEqual(new["settings"]["translate_tabs_to_spaces"], True)
        self.assertIsNone(new["settings"]["ruler"])


class TestResolveBaseBranch(unittest.TestCase):
    """R030014 / R030015 / R030016 — pick the worktree-add start point."""

    def test_existing_branch_returns_none_base(self):
        """R030014: existing local branch → no base ref needed."""
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            subprocess.run(
                ["git", "-C", tmp, "branch", "feature_x"],
                check=True, capture_output=True,
            )
            base, err = subtree._resolve_base_branch(tmp, "feature_x")
            self.assertIsNone(base)
            self.assertIsNone(err)

    def test_new_branch_uses_current_branch_as_base(self):
        """R030015: new branch → base = source's current branch."""
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp, initial_branch="master")
            base, err = subtree._resolve_base_branch(tmp, "new_feature")
            self.assertEqual(base, "master")
            self.assertIsNone(err)

    def test_detached_head_with_new_branch_errors(self):
        """R030016: detached HEAD + new branch → abort."""
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
            base, err = subtree._resolve_base_branch(tmp, "new_feature")
            self.assertIsNone(base)
            self.assertIsNotNone(err)


class TestDoCreate(unittest.TestCase):
    """End-to-end create against a real Subtree-managed git repo."""

    def _read_config(self, root):
        with open(os.path.join(root, subtree.CONFIG_FILENAME)) as f:
            return json.load(f)

    def _call_create(self, root, config, source_name, branch, base_branch_override=None):
        """Helper that bundles the path math the WindowCommand normally does."""
        repo_name = config["meta_information"]["repository_name"]
        source_dir = os.path.join(root, subtree.WORKTREES_DIRNAME, source_name)
        source_project_path = os.path.join(
            root, subtree.SUBLIME_PROJECTS_DIRNAME,
            "{}_{}.sublime-project".format(repo_name, source_name),
        )
        source_template = subtree._load_source_template(source_project_path)

        new_worktree_dir = os.path.join(root, subtree.WORKTREES_DIRNAME, branch)
        project_filename = "{}_{}.sublime-project".format(repo_name, branch)
        new_project_path = os.path.join(
            root, subtree.SUBLIME_PROJECTS_DIRNAME, project_filename
        )

        if base_branch_override is not None:
            base_branch = base_branch_override
        else:
            base_branch, err = subtree._resolve_base_branch(source_dir, branch)
            self.assertIsNone(err)

        subtree._do_create(
            source_dir, source_name, source_template,
            new_worktree_dir, new_project_path,
            branch, base_branch, project_filename, root, config,
        )
        return new_worktree_dir, new_project_path

    def test_creates_new_branch_from_source(self):
        """R030014 (negative) / R030015 / R030017 / R030018 — fresh branch path."""
        with tempfile.TemporaryDirectory() as tmp:
            root, config = _make_subtree_repo(tmp, repo_name="my_app", branch="master")
            source_dir = os.path.join(root, "worktrees", "master")
            source_head = subprocess.run(
                ["git", "-C", source_dir, "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()

            wt, proj = self._call_create(root, config, "master", "feature_1")

            # Worktree exists and tracks the new branch.
            self.assertTrue(os.path.isdir(wt))
            current = subprocess.run(
                ["git", "-C", wt, "branch", "--show-current"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            self.assertEqual(current, "feature_1")

            # New branch sits at the same commit as master.
            new_head = subprocess.run(
                ["git", "-C", wt, "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            self.assertEqual(new_head, source_head)

            # Project file written with absolute, correct path; other keys absent.
            with open(proj) as f:
                project = json.load(f)
            self.assertEqual(project, {"folders": [{"path": wt}]})
            self.assertTrue(os.path.isabs(project["folders"][0]["path"]))

            # Config entry appended with the expected fields.
            new_config = self._read_config(root)
            self.assertEqual(len(new_config["worktrees"]), 2)
            entry = new_config["worktrees"][1]
            self.assertEqual(entry["name"], "feature_1")
            self.assertEqual(entry["created_from"], "master")
            self.assertEqual(entry["project_file"], "my_app_feature_1.sublime-project")

    def test_checks_out_existing_local_branch(self):
        """R030014 — existing branch is reused, not recreated."""
        with tempfile.TemporaryDirectory() as tmp:
            root, config = _make_subtree_repo(tmp)
            source_dir = os.path.join(root, "worktrees", "master")
            subprocess.run(
                ["git", "-C", source_dir, "branch", "existing_feature"],
                check=True, capture_output=True,
            )
            before = subprocess.run(
                ["git", "-C", source_dir, "for-each-ref", "refs/heads/"],
                check=True, capture_output=True, text=True,
            ).stdout

            wt, _ = self._call_create(root, config, "master", "existing_feature")

            after = subprocess.run(
                ["git", "-C", source_dir, "for-each-ref", "refs/heads/"],
                check=True, capture_output=True, text=True,
            ).stdout
            # No new branch object created; existing_feature was already in the set.
            self.assertEqual(before, after)

            current = subprocess.run(
                ["git", "-C", wt, "branch", "--show-current"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            self.assertEqual(current, "existing_feature")

    def test_appends_to_existing_worktrees_array(self):
        """R030018 — multiple creates append in insertion order."""
        with tempfile.TemporaryDirectory() as tmp:
            root, config = _make_subtree_repo(tmp)
            self._call_create(root, config, "master", "feature_1")
            self._call_create(root, config, "master", "feature_2")

            new_config = self._read_config(root)
            names = [wt["name"] for wt in new_config["worktrees"]]
            self.assertEqual(names, ["master", "feature_1", "feature_2"])
            self.assertEqual(new_config["worktrees"][1]["created_from"], "master")
            self.assertEqual(new_config["worktrees"][2]["created_from"], "master")

    def test_rewrite_preserves_source_settings(self):
        """R030017 — non-folder source content survives the template copy."""
        with tempfile.TemporaryDirectory() as tmp:
            root, config = _make_subtree_repo(tmp)
            source_project = os.path.join(
                root, "sublime_projects", "my_app_master.sublime-project"
            )
            with open(source_project) as f:
                source_data = json.load(f)
            source_data["settings"] = {"tab_size": 2}
            source_data["folders"][0]["folder_exclude_patterns"] = [".venv"]
            with open(source_project, "w") as f:
                json.dump(source_data, f)

            _, proj = self._call_create(root, config, "master", "feature_1")
            with open(proj) as f:
                new_data = json.load(f)
            self.assertEqual(new_data["settings"], {"tab_size": 2})
            self.assertEqual(new_data["folders"][0]["folder_exclude_patterns"], [".venv"])

    def test_create_rewrites_absolute_paths_in_settings_and_build_systems(self):
        """R030017 — every string value containing the source worktree path is rewritten."""
        with tempfile.TemporaryDirectory() as tmp:
            root, config = _make_subtree_repo(tmp, repo_name="my_app", branch="master")
            source_wt = os.path.join(root, "worktrees", "master")
            source_project = os.path.join(
                root, "sublime_projects", "my_app_master.sublime-project"
            )
            with open(source_project) as f:
                source_data = json.load(f)
            source_data["folders"][0]["folder_exclude_patterns"] = [".venv", "build"]
            source_data["build_systems"] = [{
                "name": "Run script",
                "working_dir": source_wt + "/src",
                "cmd": [
                    "python",
                    source_wt + "/scripts/run.py",
                    "--config",
                    "/etc/app/config.yaml",
                ],
            }]
            source_data["settings"] = {
                "log_file": source_wt + "/logs/app.log",
                "external_tool": "/usr/local/bin/tool",
                "lint_dirs": ["src", source_wt + "/tests/unit"],
            }
            with open(source_project, "w") as f:
                json.dump(source_data, f)

            wt, proj = self._call_create(root, config, "master", "feature_1")
            with open(proj) as f:
                new_data = json.load(f)

            self.assertEqual(new_data["folders"][0]["path"], wt)
            self.assertEqual(
                new_data["folders"][0]["folder_exclude_patterns"], [".venv", "build"]
            )
            bs = new_data["build_systems"][0]
            self.assertEqual(bs["working_dir"], wt + "/src")
            self.assertEqual(bs["cmd"], [
                "python",
                wt + "/scripts/run.py",
                "--config",
                "/etc/app/config.yaml",
            ])
            self.assertEqual(new_data["settings"]["log_file"], wt + "/logs/app.log")
            self.assertEqual(
                new_data["settings"]["external_tool"], "/usr/local/bin/tool"
            )
            self.assertEqual(
                new_data["settings"]["lint_dirs"], ["src", wt + "/tests/unit"]
            )

    def test_aborts_on_multi_folder_source(self):
        """R030008 — source with len(folders) != 1 fails template load."""
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = _make_subtree_repo(tmp)
            source_project = os.path.join(
                root, "sublime_projects", "my_app_master.sublime-project"
            )
            with open(source_project) as f:
                data = json.load(f)
            data["folders"].append({"path": "/somewhere/else"})
            with open(source_project, "w") as f:
                json.dump(data, f)

            with self.assertRaises(ValueError):
                subtree._load_source_template(source_project)


if __name__ == "__main__":
    unittest.main()
