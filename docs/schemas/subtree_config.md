# `subtree_config.json` schema

The [Subtree config file](../glossary.md#subtree-config-file) lives at the [root directory](../glossary.md#root-directory) and is the source of truth for Subtree's view of the [target repository](../glossary.md#target-repository).

## Example

```json
{
    "meta_information": {
        "repository_name": "my_app",
        "main_worktree": "master"
    },
    "settings": {
        "copy_directories": [".venv", ".idea"]
    },
    "worktrees": [
        {
            "name": "master",
            "created_from": null,
            "project_file": "my_app_master.sublime-project"
        },
        {
            "name": "feature_1",
            "created_from": "master",
            "project_file": "my_app_feature_1.sublime-project"
        }
    ]
}
```

## Fields

### `meta_information.repository_name` *(string)*

Identifier set during [`init`](../requirements.md#2-init-operation); see [Repository name](../glossary.md#repository-name). Used as the prefix in every entry of `worktrees[].project_file`.

### `meta_information.main_worktree` *(string)*

[Branch name](../glossary.md#branch-name) of the [main worktree](../glossary.md#main-worktree). Set by [R020002](../requirements.md#2-init-operation).

### `worktrees` *(array of objects)*

One entry per managed worktree. Order is not significant.

### `worktrees[].name` *(string)*

Branch name tracked by the worktree. Equals the worktree directory name on disk (see [R010002](../requirements.md#1-restrictions-and-general-requirements)).

### `worktrees[].created_from` *(string or null)*

Name of the [source worktree](../glossary.md#source-worktree) (the entry in `worktrees[].name` selected as the base during [`create`](../requirements.md#3-create-operation)). `null` for the [main worktree](../glossary.md#main-worktree).

### `worktrees[].project_file` *(string)*

Basename of the matching sublime-project file under `sublime_projects/`. Computed per [R010003](../requirements.md#1-restrictions-and-general-requirements): `<repository_name>_<name>.sublime-project`, with every `/` in `<name>` replaced by `__`.

### `settings` *(object, optional)*

Repository-wide behaviour knobs. The whole object is optional; an absent or empty `settings` means "no settings configured". Unknown keys inside `settings` are reserved for future use and must be preserved on rewrite, but the current implementation will not act on them.

### `settings.copy_directories` *(array of strings, optional, default `[]`)*

Relative directory paths (relative to a worktree's root) that Subtree copies from the source worktree into the new worktree during [`create`](../requirements.md#3-create-operation) and [`open`](../requirements.md#4-open-operation). Each entry must be a relative path with no empty segments, no `.` or `..` segments, and no leading `/` or `\`.

An entry may contain glob wildcards (`*`, `?`, `[...]`), e.g. `build/_deps/*-src`. Wildcard entries are expanded against the source worktree at copy time into the set of matching **directories**; non-directory matches are ignored, and a pattern matching nothing is skipped silently. As with shell globbing, `*` does not match across `/` and does not match leading-dot segments. Matches are processed in sorted order.

At copy time (see [R030021](../requirements.md#3-create-operation) / [R040021](../requirements.md#4-open-operation)):

- Entries missing from the source worktree are skipped silently.
- Entries that are **not** gitignored in the source worktree are skipped with a warning. Subtree refuses to copy git-tracked content to avoid shadowing the new worktree's checkout.
- Entries that already exist at the target path are skipped with a warning (defensive — gitignored entries should not exist there after `git worktree add`).
- Otherwise the directory is copied recursively, preserving symlinks.

Intended for local-only artefacts such as Python virtualenvs (`.venv`), IDE caches (`.idea`), or build caches that are slow to rebuild from scratch. [`init`](../requirements.md#2-init-operation) does not write `settings` — it is up to the user to add it after initialising the repository.
