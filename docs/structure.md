# Root directory structure

After [`init`](requirements.md#2-init-operation), a Subtree-managed [target repository](glossary.md#target-repository) has the following layout at its [root directory](glossary.md#root-directory):

```
<root>/
├── subtree_config.json         # meta-information used by Subtree
├── sublime_projects/           # one .sublime-project per worktree
│   └── <repository_name>_<branch>.sublime-project
└── worktrees/                  # actual git worktrees
    └── <branch>/               # worktree directory; name == branch name (R010002)
```

## Notes

- The [main worktree](glossary.md#main-worktree) directory (`worktrees/<main-branch>/`) holds the real `.git` directory. Additional worktrees use linked `.git` files, as created by `git worktree add`.
- [Sublime project files](schemas/sublime_project.md) live in `sublime_projects/` and are named `<repository_name>_<branch>.sublime-project`, where `<repository_name>` is the value set during `init` and `<branch>` is the branch tracked by the worktree.
- Mapping from a worktree to its sublime-project file is recorded in [`subtree_config.json`](schemas/subtree_config.md) under `worktrees[].project_file`.
