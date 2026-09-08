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


class TestIsValidRelativeSubpath(unittest.TestCase):
    """`settings.copy_directories` entries must be POSIX-style relative subpaths."""

    def test_accepts_simple_name(self):
        self.assertTrue(subtree._is_valid_relative_subpath(".venv"))

    def test_accepts_nested(self):
        self.assertTrue(subtree._is_valid_relative_subpath("a/b/c"))

    def test_rejects_empty(self):
        self.assertFalse(subtree._is_valid_relative_subpath(""))

    def test_rejects_absolute(self):
        self.assertFalse(subtree._is_valid_relative_subpath("/abs"))

    def test_rejects_backslash(self):
        self.assertFalse(subtree._is_valid_relative_subpath("a\\b"))

    def test_rejects_control_chars(self):
        self.assertFalse(subtree._is_valid_relative_subpath("a\nb"))
        self.assertFalse(subtree._is_valid_relative_subpath("a\x00b"))

    def test_rejects_dot_segments(self):
        self.assertFalse(subtree._is_valid_relative_subpath("./foo"))
        self.assertFalse(subtree._is_valid_relative_subpath("foo/./bar"))
        self.assertFalse(subtree._is_valid_relative_subpath("../foo"))
        self.assertFalse(subtree._is_valid_relative_subpath("foo/../bar"))

    def test_rejects_doubled_or_trailing_slash(self):
        self.assertFalse(subtree._is_valid_relative_subpath("foo//bar"))
        self.assertFalse(subtree._is_valid_relative_subpath("foo/"))


class TestReadConfigSettings(unittest.TestCase):
    """R030004 — settings.copy_directories shape validation."""

    def _write(self, root, data):
        with open(os.path.join(root, subtree.CONFIG_FILENAME), "w") as f:
            json.dump(data, f)

    def _base_config(self):
        return {
            "meta_information": {"repository_name": "my_app", "main_worktree": "master"},
            "worktrees": [
                {"name": "master", "created_from": None,
                 "project_file": "my_app_master.sublime-project"},
            ],
        }

    def test_accepts_missing_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, self._base_config())
            subtree._read_config(tmp)  # must not raise

    def test_accepts_empty_settings_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._base_config()
            data["settings"] = {}
            self._write(tmp, data)
            subtree._read_config(tmp)

    def test_accepts_valid_copy_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._base_config()
            data["settings"] = {"copy_directories": [".venv", "build/cache"]}
            self._write(tmp, data)
            parsed = subtree._read_config(tmp)
            self.assertEqual(
                subtree._get_copy_directories(parsed), [".venv", "build/cache"]
            )

    def test_rejects_non_object_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._base_config()
            data["settings"] = ["bad"]
            self._write(tmp, data)
            with self.assertRaises(ValueError):
                subtree._read_config(tmp)

    def test_rejects_non_list_copy_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._base_config()
            data["settings"] = {"copy_directories": ".venv"}
            self._write(tmp, data)
            with self.assertRaises(ValueError):
                subtree._read_config(tmp)

    def test_rejects_non_string_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._base_config()
            data["settings"] = {"copy_directories": [".venv", 42]}
            self._write(tmp, data)
            with self.assertRaises(ValueError):
                subtree._read_config(tmp)

    def test_rejects_absolute_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._base_config()
            data["settings"] = {"copy_directories": ["/abs"]}
            self._write(tmp, data)
            with self.assertRaises(ValueError):
                subtree._read_config(tmp)

    def test_rejects_dotdot_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._base_config()
            data["settings"] = {"copy_directories": ["../escape"]}
            self._write(tmp, data)
            with self.assertRaises(ValueError):
                subtree._read_config(tmp)


class TestIsGitignored(unittest.TestCase):
    """R030021 step 2 — check-ignore wrapper."""

    def test_returns_true_for_gitignored_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            with open(os.path.join(tmp, ".gitignore"), "w") as f:
                f.write(".venv/\n")
            # `.venv/` is a directory-only pattern, so the path must actually
            # exist as a directory for `git check-ignore` to match it.
            os.mkdir(os.path.join(tmp, ".venv"))
            self.assertTrue(subtree._is_gitignored(tmp, ".venv"))

    def test_returns_false_for_tracked_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            # README.md is committed by _init_git_repo.
            self.assertFalse(subtree._is_gitignored(tmp, "README.md"))

    def test_returns_false_for_unignored_untracked_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            self.assertFalse(subtree._is_gitignored(tmp, "some_dir"))


class TestCopyListedDirectories(unittest.TestCase):
    """R030021 — directory-copy helper, exercised against real on-disk repos."""

    def _add_gitignore(self, worktree_dir, lines):
        with open(os.path.join(worktree_dir, ".gitignore"), "w") as f:
            f.write("\n".join(lines) + "\n")
        subprocess.run(
            ["git", "-C", worktree_dir, "add", ".gitignore"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", worktree_dir, "commit", "-q", "-m", "ignore"],
            check=True, capture_output=True,
        )

    def test_silent_skip_when_source_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            new = os.path.join(tmp, "new")
            os.mkdir(new)
            warnings = subtree._copy_listed_directories(tmp, new, [".venv"])
            self.assertEqual(warnings, [])
            self.assertFalse(os.path.exists(os.path.join(new, ".venv")))

    def test_copies_gitignored_directory_recursively(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            self._add_gitignore(tmp, [".venv/"])
            os.makedirs(os.path.join(tmp, ".venv", "lib"))
            with open(os.path.join(tmp, ".venv", "marker.txt"), "w") as f:
                f.write("hello")
            with open(os.path.join(tmp, ".venv", "lib", "deep.txt"), "w") as f:
                f.write("deep")

            new = os.path.join(tmp, "new")
            os.mkdir(new)
            warnings = subtree._copy_listed_directories(tmp, new, [".venv"])

            self.assertEqual(warnings, [])
            with open(os.path.join(new, ".venv", "marker.txt")) as f:
                self.assertEqual(f.read(), "hello")
            with open(os.path.join(new, ".venv", "lib", "deep.txt")) as f:
                self.assertEqual(f.read(), "deep")

    def test_preserves_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            self._add_gitignore(tmp, [".venv/"])
            os.makedirs(os.path.join(tmp, ".venv"))
            os.symlink("/etc/hostname", os.path.join(tmp, ".venv", "link"))

            new = os.path.join(tmp, "new")
            os.mkdir(new)
            warnings = subtree._copy_listed_directories(tmp, new, [".venv"])

            self.assertEqual(warnings, [])
            link = os.path.join(new, ".venv", "link")
            self.assertTrue(os.path.islink(link))
            self.assertEqual(os.readlink(link), "/etc/hostname")

    def test_warns_when_entry_not_gitignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            # Create a directory that is NOT ignored.
            os.makedirs(os.path.join(tmp, "tracked_dir"))
            with open(os.path.join(tmp, "tracked_dir", "f.txt"), "w") as f:
                f.write("x")

            new = os.path.join(tmp, "new")
            os.mkdir(new)
            warnings = subtree._copy_listed_directories(tmp, new, ["tracked_dir"])

            self.assertEqual(len(warnings), 1)
            self.assertIn("not gitignored", warnings[0])
            self.assertIn("tracked_dir", warnings[0])
            self.assertFalse(os.path.exists(os.path.join(new, "tracked_dir")))

    def test_warns_when_target_already_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            self._add_gitignore(tmp, [".venv/"])
            os.makedirs(os.path.join(tmp, ".venv"))
            with open(os.path.join(tmp, ".venv", "marker.txt"), "w") as f:
                f.write("source")

            new = os.path.join(tmp, "new")
            os.makedirs(os.path.join(new, ".venv"))  # pre-existing target
            with open(os.path.join(new, ".venv", "marker.txt"), "w") as f:
                f.write("existing")

            warnings = subtree._copy_listed_directories(tmp, new, [".venv"])

            self.assertEqual(len(warnings), 1)
            self.assertIn("already exists", warnings[0])
            with open(os.path.join(new, ".venv", "marker.txt")) as f:
                self.assertEqual(f.read(), "existing")  # not overwritten

    def test_empty_list_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            new = os.path.join(tmp, "new")
            os.mkdir(new)
            self.assertEqual(subtree._copy_listed_directories(tmp, new, []), [])

    def test_progress_callback_reports_done_and_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            self._add_gitignore(tmp, [".venv/"])
            os.makedirs(os.path.join(tmp, ".venv", "lib"))
            for name in ("a.txt", "b.txt"):
                with open(os.path.join(tmp, ".venv", name), "w") as f:
                    f.write("x")
            with open(os.path.join(tmp, ".venv", "lib", "c.txt"), "w") as f:
                f.write("x")

            new = os.path.join(tmp, "new")
            os.mkdir(new)

            calls = []

            def progress(entry, done, total):
                calls.append((entry, done, total))

            warnings = subtree._copy_listed_directories(
                tmp, new, [".venv"], progress=progress,
            )

            self.assertEqual(warnings, [])
            # First tick is (".venv", 0, 3); last tick must be (".venv", 3, 3).
            self.assertEqual(calls[0], (".venv", 0, 3))
            self.assertEqual(calls[-1], (".venv", 3, 3))
            # `done` should be monotonically non-decreasing and bounded by total.
            for entry, done, total in calls:
                self.assertEqual(entry, ".venv")
                self.assertEqual(total, 3)
                self.assertGreaterEqual(done, 0)
                self.assertLessEqual(done, 3)
            done_series = [c[1] for c in calls]
            self.assertEqual(done_series, sorted(done_series))

    def test_progress_optional_does_not_break_copy(self):
        """Sanity: without a progress callback the copy still completes."""
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            self._add_gitignore(tmp, [".venv/"])
            os.makedirs(os.path.join(tmp, ".venv"))
            with open(os.path.join(tmp, ".venv", "f.txt"), "w") as f:
                f.write("data")
            new = os.path.join(tmp, "new")
            os.mkdir(new)
            self.assertEqual(subtree._copy_listed_directories(tmp, new, [".venv"]), [])
            with open(os.path.join(new, ".venv", "f.txt")) as f:
                self.assertEqual(f.read(), "data")

    def test_creates_intermediate_dirs_for_nested_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            self._add_gitignore(tmp, ["build/cache/"])
            os.makedirs(os.path.join(tmp, "build", "cache"))
            with open(os.path.join(tmp, "build", "cache", "f.txt"), "w") as f:
                f.write("x")

            new = os.path.join(tmp, "new")
            os.mkdir(new)
            warnings = subtree._copy_listed_directories(tmp, new, ["build/cache"])

            self.assertEqual(warnings, [])
            with open(os.path.join(new, "build", "cache", "f.txt")) as f:
                self.assertEqual(f.read(), "x")

    def test_wildcard_expands_to_matching_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            self._add_gitignore(tmp, ["build/"])
            for name in ("foo-src", "bar-src"):
                os.makedirs(os.path.join(tmp, "build", "_deps", name))
                with open(os.path.join(tmp, "build", "_deps", name, "f.txt"), "w") as f:
                    f.write(name)
            # A non-matching sibling that must NOT be copied.
            os.makedirs(os.path.join(tmp, "build", "_deps", "foo-build"))
            with open(os.path.join(tmp, "build", "_deps", "foo-build", "f.txt"), "w") as f:
                f.write("nope")

            new = os.path.join(tmp, "new")
            os.mkdir(new)
            warnings = subtree._copy_listed_directories(
                tmp, new, ["build/_deps/*-src"],
            )

            self.assertEqual(warnings, [])
            for name in ("foo-src", "bar-src"):
                with open(os.path.join(new, "build", "_deps", name, "f.txt")) as f:
                    self.assertEqual(f.read(), name)
            self.assertFalse(
                os.path.exists(os.path.join(new, "build", "_deps", "foo-build"))
            )

    def test_wildcard_matching_nothing_is_silent_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            self._add_gitignore(tmp, ["build/"])
            os.makedirs(os.path.join(tmp, "build", "_deps"))

            new = os.path.join(tmp, "new")
            os.mkdir(new)
            warnings = subtree._copy_listed_directories(
                tmp, new, ["build/_deps/*-src"],
            )

            self.assertEqual(warnings, [])
            self.assertFalse(os.path.exists(os.path.join(new, "build")))

    def test_wildcard_ignores_non_directory_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            self._add_gitignore(tmp, ["build/"])
            os.makedirs(os.path.join(tmp, "build", "lib-src"))
            with open(os.path.join(tmp, "build", "lib-src", "f.txt"), "w") as f:
                f.write("dir")
            # A file matching the same pattern must be skipped (dirs only).
            with open(os.path.join(tmp, "build", "notes-src"), "w") as f:
                f.write("file")

            new = os.path.join(tmp, "new")
            os.mkdir(new)
            warnings = subtree._copy_listed_directories(tmp, new, ["build/*-src"])

            self.assertEqual(warnings, [])
            self.assertTrue(os.path.isdir(os.path.join(new, "build", "lib-src")))
            self.assertFalse(os.path.exists(os.path.join(new, "build", "notes-src")))

    def test_wildcard_warns_when_match_not_gitignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            # build/ itself is tracked, so matches are not gitignored.
            os.makedirs(os.path.join(tmp, "build", "foo-src"))
            with open(os.path.join(tmp, "build", "foo-src", "f.txt"), "w") as f:
                f.write("x")

            new = os.path.join(tmp, "new")
            os.mkdir(new)
            warnings = subtree._copy_listed_directories(tmp, new, ["build/*-src"])

            self.assertEqual(len(warnings), 1)
            self.assertIn("not gitignored", warnings[0])
            self.assertIn("foo-src", warnings[0])
            self.assertFalse(os.path.exists(os.path.join(new, "build", "foo-src")))


class TestDoCreateCopiesDirectories(unittest.TestCase):
    """R030021 / R030022 — full create with copy_directories configured."""

    def _set_copy_directories(self, root, entries):
        with open(os.path.join(root, subtree.CONFIG_FILENAME)) as f:
            data = json.load(f)
        data["settings"] = {"copy_directories": entries}
        with open(os.path.join(root, subtree.CONFIG_FILENAME), "w") as f:
            json.dump(data, f, indent=4)
            f.write("\n")
        return data

    def test_create_copies_gitignored_dir_from_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = _make_subtree_repo(tmp)
            source_dir = os.path.join(root, "worktrees", "master")
            # Set up the source: gitignored .venv with a marker file.
            with open(os.path.join(source_dir, ".gitignore"), "w") as f:
                f.write(".venv/\n")
            subprocess.run(
                ["git", "-C", source_dir, "add", ".gitignore"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", source_dir, "commit", "-q", "-m", "ignore"],
                check=True, capture_output=True,
            )
            os.makedirs(os.path.join(source_dir, ".venv"))
            with open(os.path.join(source_dir, ".venv", "marker.txt"), "w") as f:
                f.write("source-marker")

            config = self._set_copy_directories(root, [".venv"])
            repo_name = config["meta_information"]["repository_name"]
            new_worktree_dir = os.path.join(root, "worktrees", "feature_1")
            project_filename = "{}_{}.sublime-project".format(repo_name, "feature_1")
            new_project_path = os.path.join(
                root, "sublime_projects", project_filename
            )
            source_project_path = os.path.join(
                root, "sublime_projects", "my_app_master.sublime-project"
            )
            source_template = subtree._load_source_template(source_project_path)
            base_branch, _ = subtree._resolve_base_branch(source_dir, "feature_1")

            warnings = subtree._do_create(
                source_dir, "master", source_template,
                new_worktree_dir, new_project_path,
                "feature_1", base_branch, project_filename, root, config,
                copy_directories=subtree._get_copy_directories(config),
            )

            self.assertEqual(warnings, [])
            with open(os.path.join(new_worktree_dir, ".venv", "marker.txt")) as f:
                self.assertEqual(f.read(), "source-marker")

    def test_create_warns_and_skips_non_ignored_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = _make_subtree_repo(tmp)
            source_dir = os.path.join(root, "worktrees", "master")
            # Create an unignored directory in the source.
            os.makedirs(os.path.join(source_dir, "cache_dir"))
            with open(os.path.join(source_dir, "cache_dir", "x.txt"), "w") as f:
                f.write("x")

            config = self._set_copy_directories(root, ["cache_dir"])
            repo_name = config["meta_information"]["repository_name"]
            new_worktree_dir = os.path.join(root, "worktrees", "feature_1")
            project_filename = "{}_{}.sublime-project".format(repo_name, "feature_1")
            new_project_path = os.path.join(
                root, "sublime_projects", project_filename
            )
            source_template = subtree._load_source_template(os.path.join(
                root, "sublime_projects", "my_app_master.sublime-project"
            ))
            base_branch, _ = subtree._resolve_base_branch(source_dir, "feature_1")

            warnings = subtree._do_create(
                source_dir, "master", source_template,
                new_worktree_dir, new_project_path,
                "feature_1", base_branch, project_filename, root, config,
                copy_directories=subtree._get_copy_directories(config),
            )

            self.assertEqual(len(warnings), 1)
            self.assertIn("not gitignored", warnings[0])
            # R030022: worktree, project file, and config entry are still in place.
            self.assertTrue(os.path.isdir(new_worktree_dir))
            self.assertTrue(os.path.isfile(new_project_path))
            with open(os.path.join(root, subtree.CONFIG_FILENAME)) as f:
                new_config = json.load(f)
            self.assertEqual(new_config["worktrees"][-1]["name"], "feature_1")
            self.assertFalse(os.path.exists(os.path.join(new_worktree_dir, "cache_dir")))


class TestHasRewritableExtension(unittest.TestCase):
    """R030023 — name matches one of REWRITE_FILE_EXTENSIONS, case-sensitively."""

    def test_accepts_every_listed_extension(self):
        for ext in subtree.REWRITE_FILE_EXTENSIONS:
            self.assertTrue(subtree._has_rewritable_extension("thing" + ext), ext)

    def test_rejects_uppercase_extension(self):
        self.assertFalse(subtree._has_rewritable_extension("NOTES.MD"))
        self.assertFalse(subtree._has_rewritable_extension("Setup.PY"))

    def test_rejects_extensionless_name(self):
        self.assertFalse(subtree._has_rewritable_extension("activate"))
        self.assertFalse(subtree._has_rewritable_extension("Makefile"))

    def test_rejects_unlisted_extension(self):
        self.assertFalse(subtree._has_rewritable_extension("config.json"))
        self.assertFalse(subtree._has_rewritable_extension("lib.so"))

    def test_rejects_dotfile_named_exactly_like_an_extension(self):
        for ext in subtree.REWRITE_FILE_EXTENSIONS:
            self.assertFalse(subtree._has_rewritable_extension(ext), ext)


class TestRewritePathBytes(unittest.TestCase):
    """R030023 — boundary-aware byte-level substitution."""

    OLD = b"/repo/worktrees/master"
    NEW = b"/repo/worktrees/feature_1"

    def _rw(self, data):
        return subtree._rewrite_path_bytes(data, self.OLD, self.NEW)

    def test_replaces_when_followed_by_separator(self):
        self.assertEqual(
            self._rw(b"cd /repo/worktrees/master/src\n"),
            b"cd /repo/worktrees/feature_1/src\n",
        )

    def test_replaces_at_end_of_data(self):
        self.assertEqual(self._rw(b"cd /repo/worktrees/master"), b"cd /repo/worktrees/feature_1")

    def test_replaces_when_followed_by_boundary_punctuation(self):
        for nxt in (b'"', b"'", b" ", b"\n", b":", b";", b")", b","):
            self.assertEqual(
                self._rw(b"p=" + self.OLD + nxt),
                b"p=" + self.NEW + nxt,
                nxt,
            )

    def test_leaves_sibling_worktree_paths_alone(self):
        for nxt in (b"2", b"-old", b"_v2", b".bak", b"x"):
            data = b"p=" + self.OLD + nxt
            self.assertEqual(self._rw(data), data, nxt)

    def test_replaces_every_occurrence(self):
        data = self.OLD + b"/a\n" + self.OLD + b"/b\n"
        self.assertEqual(self._rw(data), self.NEW + b"/a\n" + self.NEW + b"/b\n")

    def test_mixes_replaced_and_skipped_occurrences(self):
        data = self.OLD + b"2/a\n" + self.OLD + b"/b\n"
        self.assertEqual(self._rw(data), self.OLD + b"2/a\n" + self.NEW + b"/b\n")

    def test_returns_input_unchanged_when_absent(self):
        data = b"nothing to see here"
        self.assertEqual(self._rw(data), data)

    def test_preserves_crlf_and_non_utf8_bytes(self):
        data = b"\xff\xfe binary\r\n" + self.OLD + b"/x\r\n\x00tail"
        self.assertEqual(
            self._rw(data),
            b"\xff\xfe binary\r\n" + self.NEW + b"/x\r\n\x00tail",
        )


class TestGitTrackedFiles(unittest.TestCase):
    """R030023 — enumeration of the new worktree's index via `git ls-files -z`."""

    def test_lists_committed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            os.makedirs(os.path.join(tmp, "pkg"))
            with open(os.path.join(tmp, "pkg", "mod.py"), "w") as f:
                f.write("x")
            subprocess.run(["git", "-C", tmp, "add", "pkg/mod.py"],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", tmp, "commit", "-q", "-m", "add"],
                           check=True, capture_output=True)
            self.assertEqual(
                sorted(subtree._git_tracked_files(tmp)), ["README.md", "pkg/mod.py"]
            )

    def test_excludes_untracked_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_git_repo(tmp)
            with open(os.path.join(tmp, "loose.py"), "w") as f:
                f.write("x")
            self.assertNotIn("loose.py", subtree._git_tracked_files(tmp))

    def test_raises_git_error_outside_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(subtree.GitError):
                subtree._git_tracked_files(tmp)


class TestRewriteWorktreePaths(unittest.TestCase):
    """R030023 — the rewrite pass over a new worktree."""

    def _worktree(self, tmp):
        """Return (source_dir, new_dir); new_dir is a git repo with one commit."""
        source_dir = os.path.join(tmp, "worktrees", "master")
        new_dir = os.path.join(tmp, "worktrees", "feature_1")
        os.makedirs(source_dir)
        _init_git_repo(new_dir)
        return source_dir, new_dir

    def _commit(self, repo, relpath, data):
        full = os.path.join(repo, *relpath.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(data)
        subprocess.run(["git", "-C", repo, "add", "--", relpath],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "add " + relpath],
                       check=True, capture_output=True)
        return full

    def test_rewrites_tracked_python_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir, new_dir = self._worktree(tmp)
            py = self._commit(new_dir, "run.py",
                              ('P = "%s/data"\n' % source_dir).encode())
            md = self._commit(new_dir, "docs/guide.md",
                              ("See %s/docs\n" % source_dir).encode())

            count, warnings = subtree._rewrite_worktree_paths(new_dir, source_dir)

            self.assertEqual(warnings, [])
            self.assertEqual(count, 2)
            with open(py) as f:
                self.assertEqual(f.read(), 'P = "%s/data"\n' % new_dir)
            with open(md) as f:
                self.assertEqual(f.read(), "See %s/docs\n" % new_dir)

    def test_rewritten_tracked_files_show_as_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir, new_dir = self._worktree(tmp)
            self._commit(new_dir, "run.py", ("%s/data\n" % source_dir).encode())

            subtree._rewrite_worktree_paths(new_dir, source_dir)

            status = subprocess.run(
                ["git", "-C", new_dir, "status", "--porcelain"],
                capture_output=True, text=True, check=True,
            ).stdout
            self.assertIn("run.py", status)
            self.assertTrue(status.strip().startswith("M"), status)

    def test_rewrites_file_inside_copied_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir, new_dir = self._worktree(tmp)
            venv = os.path.join(new_dir, ".venv", "bin")
            os.makedirs(venv)
            script = os.path.join(venv, "helper.sh")
            with open(script, "w") as f:
                f.write("exec %s/bin/tool\n" % source_dir)

            count, warnings = subtree._rewrite_worktree_paths(
                new_dir, source_dir, copied_dirs=[".venv"]
            )

            self.assertEqual(warnings, [])
            self.assertEqual(count, 1)
            with open(script) as f:
                self.assertEqual(f.read(), "exec %s/bin/tool\n" % new_dir)

    def test_ignores_untracked_file_outside_copied_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir, new_dir = self._worktree(tmp)
            loose = os.path.join(new_dir, "loose.py")
            with open(loose, "w") as f:
                f.write("%s/x\n" % source_dir)

            count, warnings = subtree._rewrite_worktree_paths(new_dir, source_dir)

            self.assertEqual((count, warnings), (0, []))
            with open(loose) as f:
                self.assertEqual(f.read(), "%s/x\n" % source_dir)

    def test_leaves_sibling_worktree_path_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir, new_dir = self._worktree(tmp)
            body = "a=%s2/x\nb=%s/x\n" % (source_dir, source_dir)
            f_path = self._commit(new_dir, "paths.txt", body.encode())

            count, _ = subtree._rewrite_worktree_paths(new_dir, source_dir)

            self.assertEqual(count, 1)
            with open(f_path) as f:
                self.assertEqual(f.read(), "a=%s2/x\nb=%s/x\n" % (source_dir, new_dir))

    def test_skips_uppercase_extension_and_extensionless_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir, new_dir = self._worktree(tmp)
            body = ("%s/x\n" % source_dir).encode()
            upper = self._commit(new_dir, "NOTES.MD", body)
            plain = self._commit(new_dir, "activate", body)

            count, warnings = subtree._rewrite_worktree_paths(new_dir, source_dir)

            self.assertEqual((count, warnings), (0, []))
            for path in (upper, plain):
                with open(path, "rb") as f:
                    self.assertEqual(f.read(), body)

    def test_skips_symlinked_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir, new_dir = self._worktree(tmp)
            os.makedirs(os.path.join(new_dir, ".venv"))
            target = os.path.join(tmp, "outside.py")
            with open(target, "w") as f:
                f.write("%s/x\n" % source_dir)
            link = os.path.join(new_dir, ".venv", "linked.py")
            os.symlink(target, link)

            count, warnings = subtree._rewrite_worktree_paths(
                new_dir, source_dir, copied_dirs=[".venv"]
            )

            self.assertEqual((count, warnings), (0, []))
            self.assertTrue(os.path.islink(link))
            with open(target) as f:
                self.assertEqual(f.read(), "%s/x\n" % source_dir)

    def test_preserves_crlf_and_binary_bytes_in_rewritten_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir, new_dir = self._worktree(tmp)
            body = b"\xff\xfe\r\n" + source_dir.encode() + b"/x\r\n\x00"
            path = self._commit(new_dir, "data.txt", body)

            count, warnings = subtree._rewrite_worktree_paths(new_dir, source_dir)

            self.assertEqual((count, warnings), (1, []))
            with open(path, "rb") as f:
                self.assertEqual(
                    f.read(), b"\xff\xfe\r\n" + new_dir.encode() + b"/x\r\n\x00"
                )

    def test_preserves_executable_bit(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir, new_dir = self._worktree(tmp)
            path = self._commit(new_dir, "tool.sh", ("%s/x\n" % source_dir).encode())
            os.chmod(path, 0o755)

            subtree._rewrite_worktree_paths(new_dir, source_dir)

            self.assertTrue(os.stat(path).st_mode & 0o111)

    def test_counts_each_file_once_when_tracked_and_in_copied_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir, new_dir = self._worktree(tmp)
            self._commit(new_dir, "tools/x.py", ("%s/a\n" % source_dir).encode())

            count, warnings = subtree._rewrite_worktree_paths(
                new_dir, source_dir, copied_dirs=["tools"]
            )

            self.assertEqual((count, warnings), (1, []))

    def test_warns_once_and_continues_when_ls_files_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = os.path.join(tmp, "worktrees", "master")
            new_dir = os.path.join(tmp, "worktrees", "feature_1")
            os.makedirs(source_dir)
            os.makedirs(os.path.join(new_dir, ".venv"))
            script = os.path.join(new_dir, ".venv", "run.sh")
            with open(script, "w") as f:
                f.write("%s/x\n" % source_dir)

            count, warnings = subtree._rewrite_worktree_paths(
                new_dir, source_dir, copied_dirs=[".venv"]
            )

            self.assertEqual(len(warnings), 1)
            self.assertIn("tracked files", warnings[0])
            self.assertEqual(count, 1)
            with open(script) as f:
                self.assertEqual(f.read(), "%s/x\n" % new_dir)

    def test_warns_and_names_unreadable_file(self):
        if os.geteuid() == 0:
            self.skipTest("root bypasses file permissions")
        with tempfile.TemporaryDirectory() as tmp:
            source_dir, new_dir = self._worktree(tmp)
            path = self._commit(new_dir, "locked.py", ("%s/x\n" % source_dir).encode())
            os.chmod(path, 0o000)
            try:
                count, warnings = subtree._rewrite_worktree_paths(new_dir, source_dir)
            finally:
                os.chmod(path, 0o644)

            self.assertEqual(count, 0)
            self.assertEqual(len(warnings), 1)
            self.assertIn("locked.py", warnings[0])

    def test_missing_copied_dir_is_silently_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir, new_dir = self._worktree(tmp)
            count, warnings = subtree._rewrite_worktree_paths(
                new_dir, source_dir, copied_dirs=["nope"]
            )
            self.assertEqual((count, warnings), (0, []))


class TestDoCreateRewritesPaths(unittest.TestCase):
    """R030023 — full create rewrites the new worktree's files."""

    def _prepare(self, tmp, copy_directories=None):
        root, config = _make_subtree_repo(tmp)
        if copy_directories is not None:
            config["settings"] = {"copy_directories": copy_directories}
            with open(os.path.join(root, subtree.CONFIG_FILENAME), "w") as f:
                json.dump(config, f, indent=4)
                f.write("\n")
        return root, config

    def _create(self, root, config, branch="feature_1", copy_directories=(),
                on_rewritten=None):
        source_dir = os.path.join(root, "worktrees", "master")
        repo_name = config["meta_information"]["repository_name"]
        project_filename = "{}_{}.sublime-project".format(repo_name, branch)
        new_worktree_dir = os.path.join(root, "worktrees", branch)
        new_project_path = os.path.join(root, "sublime_projects", project_filename)
        source_template = subtree._load_source_template(os.path.join(
            root, "sublime_projects", "my_app_master.sublime-project"
        ))
        base_branch, _ = subtree._resolve_base_branch(source_dir, branch)
        warnings = subtree._do_create(
            source_dir, "master", source_template,
            new_worktree_dir, new_project_path,
            branch, base_branch, project_filename, root, config,
            copy_directories=copy_directories,
            on_rewritten=on_rewritten,
        )
        return new_worktree_dir, warnings

    def test_rewrites_tracked_script_and_doc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, config = self._prepare(tmp)
            source_dir = os.path.join(root, "worktrees", "master")
            with open(os.path.join(source_dir, "run.py"), "w") as f:
                f.write('ROOT = "%s"\n' % source_dir)
            with open(os.path.join(source_dir, "GUIDE.md"), "w") as f:
                f.write("cd %s\n" % source_dir)
            subprocess.run(["git", "-C", source_dir, "add", "run.py", "GUIDE.md"],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", source_dir, "commit", "-q", "-m", "scripts"],
                           check=True, capture_output=True)

            new_dir, warnings = self._create(root, config)

            self.assertEqual(warnings, [])
            with open(os.path.join(new_dir, "run.py")) as f:
                self.assertEqual(f.read(), 'ROOT = "%s"\n' % new_dir)
            with open(os.path.join(new_dir, "GUIDE.md")) as f:
                self.assertEqual(f.read(), "cd %s\n" % new_dir)

    def test_reports_rewritten_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, config = self._prepare(tmp)
            source_dir = os.path.join(root, "worktrees", "master")
            with open(os.path.join(source_dir, "run.py"), "w") as f:
                f.write("%s\n" % source_dir)
            subprocess.run(["git", "-C", source_dir, "add", "run.py"],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", source_dir, "commit", "-q", "-m", "s"],
                           check=True, capture_output=True)
            seen = []

            self._create(root, config, on_rewritten=seen.append)

            self.assertEqual(seen, [1])

    def test_rewrites_file_inside_copied_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, config = self._prepare(tmp, copy_directories=[".venv"])
            source_dir = os.path.join(root, "worktrees", "master")
            with open(os.path.join(source_dir, ".gitignore"), "w") as f:
                f.write(".venv/\n")
            subprocess.run(["git", "-C", source_dir, "add", ".gitignore"],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", source_dir, "commit", "-q", "-m", "ignore"],
                           check=True, capture_output=True)
            os.makedirs(os.path.join(source_dir, ".venv", "bin"))
            with open(os.path.join(source_dir, ".venv", "bin", "go.sh"), "w") as f:
                f.write("exec %s/bin/python\n" % source_dir)

            new_dir, warnings = self._create(
                root, config, copy_directories=[".venv"]
            )

            self.assertEqual(warnings, [])
            with open(os.path.join(new_dir, ".venv", "bin", "go.sh")) as f:
                self.assertEqual(f.read(), "exec %s/bin/python\n" % new_dir)

    def test_does_not_rewrite_skipped_copy_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, config = self._prepare(tmp, copy_directories=["cache_dir"])
            source_dir = os.path.join(root, "worktrees", "master")
            os.makedirs(os.path.join(source_dir, "cache_dir"))
            with open(os.path.join(source_dir, "cache_dir", "x.sh"), "w") as f:
                f.write("%s\n" % source_dir)

            new_dir, warnings = self._create(
                root, config, copy_directories=["cache_dir"]
            )

            self.assertEqual(len(warnings), 1)
            self.assertIn("not gitignored", warnings[0])
            self.assertFalse(os.path.exists(os.path.join(new_dir, "cache_dir")))


if __name__ == "__main__":
    unittest.main()
