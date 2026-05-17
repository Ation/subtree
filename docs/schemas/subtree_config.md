# `subtree_config.json` schema

The [Subtree config file](../glossary.md#subtree-config-file) lives at the [root directory](../glossary.md#root-directory) and is the source of truth for Subtree's view of the [target repository](../glossary.md#target-repository).

## Example

```json
{
    "meta_information": {
        "repository_name": "my_app",
        "main_worktree": "master"
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

Name of the parent worktree's branch (the branch this worktree was branched from). `null` for the main worktree.

### `worktrees[].project_file` *(string)*

Basename of the matching sublime-project file under `sublime_projects/`. By convention this is `<repository_name>_<name>.sublime-project`.
