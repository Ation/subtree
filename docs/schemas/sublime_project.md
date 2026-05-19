# Sublime project file schema

Subtree writes one `.sublime-project` file per worktree, stored under `sublime_projects/` and named `<repository_name>_<branch>.sublime-project` (see [structure](../structure.md)).

## Initial structure

When created, the file contains a single folder entry pointing at the [worktree directory](../glossary.md#worktree-directory):

```json
{
    "folders": [
        { "path": "<absolute path to worktree directory>" }
    ]
}
```

## Notes

- Subtree writes **absolute** paths in `folders[].path` so the project file is independent of where Sublime Text is launched from. Sublime also accepts relative paths, but Subtree does not use them in the initial file.
- After creation, the file may be edited freely by the user (additional folders, build systems, settings, etc.).
- When [`create`](../requirements.md#3-create-operation) or [`open`](../requirements.md#4-open-operation) uses an existing project file as a template, Subtree rewrites **every string value** in the JSON, recursively (any field, any depth, inside lists and nested objects), replacing occurrences of the source worktree directory's absolute path with the new worktree directory's absolute path (R030017 / R040017). The replacement is a literal substring swap; relative paths and absolute paths outside the source worktree are untouched, and JSON keys are never modified.
- The substring swap is naive: a path like `/repo/worktrees/master_old/...` would also be rewritten when the source worktree is `/repo/worktrees/master`, because the source path appears as a literal prefix. If a project file references sibling worktrees by absolute path, edit the resulting file manually.
- Relative paths (e.g. `"src"`, `"./scripts"`, `".venv"`) are unaffected, because they cannot contain an absolute path as a substring.
- [`create`](../requirements.md#3-create-operation) requires the source file to contain exactly one entry in `folders` (R030008); a user who adds additional folders to a project file makes it unusable as a `create` source.

## Worked example of the rewrite

Source worktree `master` lives at `/repo/worktrees/master`. A new worktree `feature/foo` is being created at `/repo/worktrees/feature/foo`. The source project file references the source worktree directly, in subdirectories several levels deep, and in files inside those subdirectories:

```json
{
    "folders": [
        {
            "path": "/repo/worktrees/master",
            "folder_exclude_patterns": [".venv", "build"]
        }
    ],
    "build_systems": [
        {
            "name": "Run script",
            "working_dir": "/repo/worktrees/master/src",
            "cmd": ["python", "/repo/worktrees/master/scripts/run.py", "--config", "/etc/app/config.yaml"]
        }
    ],
    "settings": {
        "log_file": "/repo/worktrees/master/logs/app.log",
        "external_tool": "/usr/local/bin/tool",
        "lint_dirs": ["src", "/repo/worktrees/master/tests/unit"]
    }
}
```

After the rewrite, every occurrence of `/repo/worktrees/master` inside a string value has been replaced with `/repo/worktrees/feature/foo`:

```json
{
    "folders": [
        {
            "path": "/repo/worktrees/feature/foo",
            "folder_exclude_patterns": [".venv", "build"]
        }
    ],
    "build_systems": [
        {
            "name": "Run script",
            "working_dir": "/repo/worktrees/feature/foo/src",
            "cmd": ["python", "/repo/worktrees/feature/foo/scripts/run.py", "--config", "/etc/app/config.yaml"]
        }
    ],
    "settings": {
        "log_file": "/repo/worktrees/feature/foo/logs/app.log",
        "external_tool": "/usr/local/bin/tool",
        "lint_dirs": ["src", "/repo/worktrees/feature/foo/tests/unit"]
    }
}
```

What changed and what didn't:

- `folders[0].path`, `build_systems[0].working_dir`, `build_systems[0].cmd[1]`, `settings.log_file`, `settings.lint_dirs[1]` — all rewritten, including deep file paths and paths embedded inside heterogeneous lists.
- `folder_exclude_patterns`, `settings.lint_dirs[0]` (`"src"`) — unchanged (relative paths).
- `settings.external_tool` (`"/usr/local/bin/tool"`) and `build_systems[0].cmd[3]` (`"/etc/app/config.yaml"`) — unchanged (absolute paths that don't contain the source worktree path as a substring).
- JSON keys (`"folders"`, `"path"`, `"build_systems"`, …) — unchanged (only values are scanned).
