# Root directory structure

After [`init`](requirements.md#2-init-operation), a Subtree-managed [target repository](glossary.md#target-repository) has the following layout at its [root directory](glossary.md#root-directory):

```
<root>/
├── subtree_config.json                                   # meta-information used by Subtree
├── sublime_projects/                                     # one .sublime-project per worktree (flat)
│   ├── <repository_name>_master.sublime-project
│   └── <repository_name>_feature__foo.sublime-project    # branch "feature/foo" — '/' replaced by '__'
└── worktrees/                                            # actual git worktrees (nested per branch)
    ├── master/
    └── feature/
        └── foo/                                          # branch "feature/foo" (R010002)
```

## Notes

- The [main worktree](glossary.md#main-worktree) directory (`worktrees/<main-branch>/`) holds the real `.git` directory. Additional worktrees, added by [`create`](requirements.md#3-create-operation) or [`open`](requirements.md#4-open-operation), appear under `worktrees/` and use linked `.git` files (as created by `git worktree add`); each one has a matching sublime-project file under `sublime_projects/`.
- A worktree's path under `worktrees/` equals its [branch name](glossary.md#branch-name); branches with `/` produce nested subdirectories (see [R010002](requirements.md#1-restrictions-and-general-requirements)).
- [Sublime project files](schemas/sublime_project.md) live flat under `sublime_projects/` and are named `<repository_name>_<branch>.sublime-project`, with every `/` in the branch name replaced by `__` (see [R010003](requirements.md#1-restrictions-and-general-requirements)).
- Mapping from a worktree to its sublime-project file is recorded in [`subtree_config.json`](schemas/subtree_config.md) under `worktrees[].project_file`.
