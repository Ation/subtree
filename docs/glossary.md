# Glossary

Terms used throughout Subtree's documentation and source code. Other docs assume these definitions.

### Subtree

Name of this plugin / project.

### Target repository

Any git repository that Subtree operates on.

### Repository name

Identifier set during [`init`](requirements.md#2-init-operation). Used as the prefix for every sublime-project file Subtree creates (see [sublime project filename convention](structure.md)).

### Root directory

Top-level directory of the target repository. After `init`, it holds [`subtree_config.json`](schemas/subtree_config.md), [`sublime_projects/`](structure.md), and [`worktrees/`](structure.md).

### Current directory

Directory Subtree is currently acting on — typically the working directory of the user's editor session. (Not to be confused with the `git subtree` git subcommand, which is unrelated to this project.)

### Worktree directory

Filesystem path of a single git worktree, e.g. `worktrees/master`. Its directory name equals the branch name it tracks (see [R010002](requirements.md#1-restrictions-and-general-requirements)).

### Branch name

Name of the git branch checked out in a worktree. By [R010002](requirements.md#1-restrictions-and-general-requirements) it equals the worktree directory name.

### Current project

The `.sublime-project` file corresponding to the worktree that contains the current directory.

### Main worktree

Worktree that owns the `.git` directory and tracks the repository's main (master) branch. Cannot be removed by Subtree ([R010001](requirements.md#1-restrictions-and-general-requirements)).

### Subtree config file

[`subtree_config.json`](schemas/subtree_config.md) at the root directory; the source of truth for Subtree's view of the repository.
