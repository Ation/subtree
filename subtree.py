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
        sublime.set_timeout(lambda: self._switch_window(project_path), 0)

    def _switch_window(self, project_path):
        try:
            subprocess.Popen(["subl", "--project", project_path])
        except FileNotFoundError:
            sublime.error_message(
                "Subtree: Init complete, but `subl` was not found on PATH. "
                "Open the new project manually:\n{}".format(project_path)
            )
            return
        self.window.run_command("close_window")


class SubtreeCreateCommand(sublime_plugin.WindowCommand):
    def run(self):
        pass


class SubtreeOpenCommand(sublime_plugin.WindowCommand):
    def run(self):
        pass


class SubtreeRemoveCommand(sublime_plugin.WindowCommand):
    def run(self):
        pass
