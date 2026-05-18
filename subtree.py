import copy
import json
import os
import re
import subprocess

import sublime
import sublime_plugin


CONFIG_FILENAME = "subtree_config.json"
WORKTREES_DIRNAME = "worktrees"
SUBLIME_PROJECTS_DIRNAME = "sublime_projects"
RESERVED_DIRNAMES = (WORKTREES_DIRNAME, SUBLIME_PROJECTS_DIRNAME)

_INVALID_REPO_NAME_RE = re.compile(r"[\\/]|[\x00-\x1f]")


class GitError(RuntimeError):
    pass


def _git_branch(cwd):
    """Return the current branch name in `cwd`, or None if HEAD is detached."""
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "branch", "--show-current"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise GitError("`git` was not found on PATH.")
    if result.returncode != 0:
        raise GitError("git failed: " + (result.stderr.strip() or "unknown error"))
    branch = result.stdout.strip()
    return branch or None


def _validate_repo_name(name):
    """Return an error message if `name` is invalid (R020006), else None."""
    if not name:
        return "Repository name must not be empty."
    if _INVALID_REPO_NAME_RE.search(name):
        return "Repository name must not contain '/', '\\', or control characters."
    return None


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
        f.write("\n")


def _preflight(target):
    """Validate `target` for init. Returns (error_message, r_code) or (None, None)."""
    if not os.path.isdir(os.path.join(target, ".git")):
        return ("Not a git working tree: no .git directory at {}.".format(target), "R020001")
    if os.path.exists(os.path.join(target, CONFIG_FILENAME)):
        return ("Already initialized: {} exists.".format(CONFIG_FILENAME), "R020007")
    for name in RESERVED_DIRNAMES:
        if os.path.exists(os.path.join(target, name)):
            return ("Reserved name collision: {}/ already exists.".format(name), "R020008")
    return (None, None)


def _do_init(target, repo_name, branch):
    """Perform the conversion described by R020003. Returns the absolute path
    of the created sublime-project file. Raises OSError on failure."""
    entries = os.listdir(target)
    worktrees_dir = os.path.join(target, WORKTREES_DIRNAME)
    sublime_projects_dir = os.path.join(target, SUBLIME_PROJECTS_DIRNAME)
    main_worktree_dir = os.path.join(worktrees_dir, branch)

    os.mkdir(worktrees_dir)
    os.mkdir(sublime_projects_dir)
    os.makedirs(main_worktree_dir)

    for entry in entries:
        os.rename(
            os.path.join(target, entry),
            os.path.join(main_worktree_dir, entry),
        )

    project_filename = "{}_{}.sublime-project".format(repo_name, branch)
    config = {
        "meta_information": {
            "repository_name": repo_name,
            "main_worktree": branch,
        },
        "worktrees": [
            {
                "name": branch,
                "created_from": None,
                "project_file": project_filename,
            },
        ],
    }
    _write_json(os.path.join(target, CONFIG_FILENAME), config)

    project_path = os.path.join(sublime_projects_dir, project_filename)
    _write_json(project_path, {"folders": [{"path": main_worktree_dir}]})
    return project_path


def _validate_branch_name(name):
    """Return an error message if `name` is invalid (R030010), else None.

    Uses the same charset rule as `_validate_repo_name` because the branch
    name is reused unchanged as both a worktree directory name (per R010002)
    and as a filename component of the sublime-project file.
    """
    if not name:
        return "Branch name must not be empty."
    if _INVALID_REPO_NAME_RE.search(name):
        return "Branch name must not contain '/', '\\', or control characters."
    return None


def _find_root(start_dir):
    """Walk upward from `start_dir` until a directory containing CONFIG_FILENAME
    is found (R030002). Return its absolute path, or None if none is found
    before reaching the filesystem root."""
    current = os.path.abspath(start_dir)
    while True:
        if os.path.isfile(os.path.join(current, CONFIG_FILENAME)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _read_config(root):
    """Read and minimally validate subtree_config.json at `root` (R030004).

    Returns the parsed dict. Raises ValueError on JSON or structural errors;
    lets OSError bubble.
    """
    with open(os.path.join(root, CONFIG_FILENAME), "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError("subtree_config.json is not valid JSON: {}".format(e))
    if not isinstance(data, dict):
        raise ValueError("subtree_config.json must contain a JSON object.")
    meta = data.get("meta_information")
    if not isinstance(meta, dict):
        raise ValueError("subtree_config.json is missing 'meta_information'.")
    if not isinstance(meta.get("repository_name"), str):
        raise ValueError("subtree_config.json: meta_information.repository_name must be a string.")
    if not isinstance(meta.get("main_worktree"), str):
        raise ValueError("subtree_config.json: meta_information.main_worktree must be a string.")
    worktrees = data.get("worktrees")
    if not isinstance(worktrees, list):
        raise ValueError("subtree_config.json: 'worktrees' must be an array.")
    for i, entry in enumerate(worktrees):
        if not isinstance(entry, dict):
            raise ValueError("subtree_config.json: worktrees[{}] must be an object.".format(i))
        for key in ("name", "project_file"):
            if not isinstance(entry.get(key), str):
                raise ValueError(
                    "subtree_config.json: worktrees[{}].{} must be a string.".format(i, key)
                )
        if "created_from" not in entry:
            raise ValueError(
                "subtree_config.json: worktrees[{}].created_from is missing.".format(i)
            )
        cf = entry["created_from"]
        if cf is not None and not isinstance(cf, str):
            raise ValueError(
                "subtree_config.json: worktrees[{}].created_from must be string or null.".format(i)
            )
    return data


def _local_branch_exists(repo_cwd, branch):
    """Return True iff `branch` resolves as a local git branch from `repo_cwd` (R030014)."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_cwd, "show-ref", "--verify", "--quiet",
             "refs/heads/" + branch],
            capture_output=True,
        )
    except FileNotFoundError:
        raise GitError("`git` was not found on PATH.")
    return result.returncode == 0


def _git_worktree_add(source_cwd, new_path, branch, base_branch):
    """Invoke `git worktree add` (R030014 / R030015).

    If `base_branch` is None, check out the existing local `branch` into
    `new_path`. Otherwise, create branch `branch` from `base_branch` at
    `new_path`. Raises GitError(stderr) on non-zero exit.
    """
    if base_branch is None:
        cmd = ["git", "-C", source_cwd, "worktree", "add", new_path, branch]
    else:
        cmd = ["git", "-C", source_cwd, "worktree", "add", "-b", branch, new_path, base_branch]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise GitError("`git` was not found on PATH.")
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or "git worktree add failed.")


def _load_source_template(project_path):
    """Read and validate the source sublime-project file (R030008).

    Returns the parsed dict. Raises ValueError if the file does not exist,
    is unparseable, lacks a `folders` array, or `folders` does not contain
    exactly one entry.
    """
    try:
        with open(project_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ValueError("Source sublime-project file not found: {}".format(project_path))
    except json.JSONDecodeError as e:
        raise ValueError("Source sublime-project file is not valid JSON: {}".format(e))
    if not isinstance(data, dict):
        raise ValueError("Source sublime-project file must contain a JSON object.")
    folders = data.get("folders")
    if not isinstance(folders, list):
        raise ValueError("Source sublime-project file has no 'folders' array.")
    if len(folders) != 1:
        raise ValueError(
            "Source sublime-project file must have exactly one folder entry "
            "(found {}).".format(len(folders))
        )
    if not isinstance(folders[0], dict):
        raise ValueError("Source sublime-project file: folders[0] must be an object.")
    return data


def _rewrite_template(source_data, new_worktree_path):
    """Return a deep copy of `source_data` with folders[0].path replaced (R030017)."""
    new_data = copy.deepcopy(source_data)
    new_data["folders"][0]["path"] = new_worktree_path
    return new_data


def _resolve_base_branch(source_dir, branch):
    """Decide the `base_branch` argument for `_git_worktree_add`.

    Returns (base_branch, error_message). `base_branch` is None when an
    existing local branch should be checked out (R030014). Otherwise it is
    the source worktree's current branch, used as the start point for a new
    branch (R030015). On detached HEAD with no existing branch match,
    returns (None, <R030016 error>).
    """
    if _local_branch_exists(source_dir, branch):
        return None, None  # R030014: existing branch path
    current = _git_branch(source_dir)
    if current is None:
        return None, (
            "Source worktree has detached HEAD; cannot derive a new branch."
        )
    return current, None


def _do_create(source_dir, source_name, source_template,
               new_worktree_dir, new_project_path,
               branch, base_branch, project_filename, root, config):
    """Side-effecting orchestration. Order matters:

    1. `git worktree add` (R030014 / R030015) — failure leaves Subtree state untouched.
    2. Write new sublime-project file (R030017).
    3. Append config entry and rewrite subtree_config.json (R030018).

    Raises GitError on git failure (no Subtree files written), OSError on a
    later write failure (worktree dir already exists on disk).
    """
    _git_worktree_add(source_dir, new_worktree_dir, branch, base_branch)

    new_project = _rewrite_template(source_template, new_worktree_dir)
    _write_json(new_project_path, new_project)

    config["worktrees"].append({
        "name": branch,
        "created_from": source_name,
        "project_file": project_filename,
    })
    _write_json(os.path.join(root, CONFIG_FILENAME), config)


def _open_project_and_close(window, project_path, op_label):
    """Open `project_path` via `subl --project` and close `window` (R020010 / R030019)."""
    try:
        subprocess.Popen(["subl", "--project", project_path])
    except FileNotFoundError:
        sublime.error_message(
            "Subtree: {} complete, but `subl` was not found on PATH. "
            "Open the new project manually:\n{}".format(op_label, project_path)
        )
        return
    window.run_command("close_window")


class SubtreeInitCommand(sublime_plugin.WindowCommand):
    def run(self):
        folders = self.window.folders()
        if not folders:
            sublime.error_message(
                "Subtree: Init requires a folder open in the window (R020004)."
            )
            return
        target = folders[0]

        err, rcode = _preflight(target)
        if err is not None:
            sublime.error_message("Subtree: {} ({})".format(err, rcode))
            return

        try:
            branch = _git_branch(target)
        except GitError as e:
            sublime.error_message("Subtree: {}".format(e))
            return
        if branch is None:
            sublime.error_message(
                "Subtree: Cannot determine current branch (detached HEAD?). "
                "Check out a branch before running Init (R020009)."
            )
            return

        default_name = os.path.basename(os.path.normpath(target))
        self.window.show_input_panel(
            "Repository name:",
            default_name,
            lambda value: self._on_name(target, branch, value),
            None,
            None,
        )

    def _on_name(self, target, branch, value):
        name = value.strip()
        err = _validate_repo_name(name)
        if err is not None:
            sublime.error_message("Subtree: {} (R020006)".format(err))
            return
        sublime.set_timeout_async(
            lambda: self._run_conversion(target, name, branch), 0
        )

    def _run_conversion(self, target, repo_name, branch):
        try:
            project_path = _do_init(target, repo_name, branch)
        except OSError as e:
            sublime.error_message(
                "Subtree: Init failed mid-conversion: {}.\n\n"
                "The repository may be in a partial state; inspect {} manually.".format(
                    e, target
                )
            )
            return
        sublime.set_timeout(
            lambda: _open_project_and_close(self.window, project_path, "Init"), 0
        )


class SubtreeCreateCommand(sublime_plugin.WindowCommand):
    def run(self):
        # R030001: must have a folder open.
        folders = self.window.folders()
        if not folders:
            sublime.error_message(
                "Subtree: Create requires a folder open in the window (R030001)."
            )
            return

        # R030002 / R030003: locate root.
        root = _find_root(folders[0])
        if root is None:
            sublime.error_message(
                "Subtree: No {} found at or above {} (R030003).".format(
                    CONFIG_FILENAME, folders[0]
                )
            )
            return

        # R030004: read + validate config.
        try:
            config = _read_config(root)
        except (OSError, ValueError) as e:
            sublime.error_message("Subtree: {} (R030004)".format(e))
            return

        # R030005: source worktree quick panel.
        names = [wt["name"] for wt in config["worktrees"]]
        self.window.show_quick_panel(
            names,
            lambda idx: self._on_source_picked(root, config, idx),
        )

    def _on_source_picked(self, root, config, idx):
        if idx < 0:
            return  # R030006: user dismissed.

        source_entry = config["worktrees"][idx]
        source_name = source_entry["name"]
        source_dir = os.path.join(root, WORKTREES_DIRNAME, source_name)

        # R030007: source dir must exist.
        if not os.path.isdir(source_dir):
            sublime.error_message(
                "Subtree: Source worktree directory missing: {} (R030007).".format(source_dir)
            )
            return

        # R030008: validate source template up-front (before prompting for a name).
        source_project_path = os.path.join(
            root, SUBLIME_PROJECTS_DIRNAME, source_entry["project_file"]
        )
        try:
            source_template = _load_source_template(source_project_path)
        except ValueError as e:
            sublime.error_message("Subtree: {} (R030008)".format(e))
            return

        # R030009: prompt for branch name.
        self.window.show_input_panel(
            "New branch / worktree name:",
            "",
            lambda value: self._on_branch_entered(
                root, config, source_name, source_dir, source_template, value
            ),
            None,
            None,
        )

    def _on_branch_entered(self, root, config, source_name, source_dir, source_template, value):
        branch = value.strip()

        # R030010: charset validation.
        err = _validate_branch_name(branch)
        if err is not None:
            sublime.error_message("Subtree: {} (R030010)".format(err))
            return

        # R030011: duplicate name.
        existing = {wt["name"] for wt in config["worktrees"]}
        if branch in existing:
            sublime.error_message(
                "Subtree: A worktree named '{}' already exists in {} (R030011).".format(
                    branch, CONFIG_FILENAME
                )
            )
            return

        repo_name = config["meta_information"]["repository_name"]
        new_worktree_dir = os.path.join(root, WORKTREES_DIRNAME, branch)
        project_filename = "{}_{}.sublime-project".format(repo_name, branch)
        new_project_path = os.path.join(root, SUBLIME_PROJECTS_DIRNAME, project_filename)

        # R030012 / R030013: filesystem collisions.
        if os.path.exists(new_worktree_dir):
            sublime.error_message(
                "Subtree: Worktree directory already exists: {} (R030012).".format(new_worktree_dir)
            )
            return
        if os.path.exists(new_project_path):
            sublime.error_message(
                "Subtree: Sublime-project file already exists: {} (R030013).".format(new_project_path)
            )
            return

        sublime.set_timeout_async(
            lambda: self._run_create(
                root, config, source_name, source_dir, source_template,
                branch, new_worktree_dir, new_project_path, project_filename,
            ),
            0,
        )

    def _run_create(self, root, config, source_name, source_dir, source_template,
                    branch, new_worktree_dir, new_project_path, project_filename):
        # R030014 / R030015 / R030016: pick base branch strategy.
        try:
            base_branch, err = _resolve_base_branch(source_dir, branch)
        except GitError as e:
            sublime.error_message("Subtree: {}".format(e))
            return
        if err is not None:
            sublime.error_message("Subtree: {} (R030016)".format(err))
            return

        try:
            _do_create(
                source_dir, source_name, source_template,
                new_worktree_dir, new_project_path,
                branch, base_branch, project_filename, root, config,
            )
        except GitError as e:
            sublime.error_message(
                "Subtree: git worktree add failed: {} (R030020)".format(e)
            )
            return
        except OSError as e:
            sublime.error_message(
                "Subtree: Create succeeded in git but failed writing Subtree files: {}.\n\n"
                "Inspect {} manually.".format(e, root)
            )
            return

        sublime.set_timeout(
            lambda: _open_project_and_close(self.window, new_project_path, "Create"), 0
        )


class SubtreeOpenCommand(sublime_plugin.WindowCommand):
    def run(self):
        pass


class SubtreeRemoveCommand(sublime_plugin.WindowCommand):
    def run(self):
        pass
