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

Filesystem path of a single git worktree. Its path under `worktrees/` equals the branch name it tracks (see [R010002](requirements.md#1-restrictions-and-general-requirements)), with `/` interpreted as a path separator. Examples: `worktrees/master`, `worktrees/feature/foo`.

### Branch name

Name of the git branch checked out in a worktree. By [R010002](requirements.md#1-restrictions-and-general-requirements) it equals the worktree directory's path under `worktrees/`. `/` is allowed and creates nested directories. The corresponding sublime-project filename substitutes `/` with `__` (see [R010003](requirements.md#1-restrictions-and-general-requirements)).

### Current project

The `.sublime-project` file corresponding to the worktree that contains the current directory.

### Main worktree

Worktree that owns the `.git` directory and tracks the repository's main (master) branch. Cannot be removed by Subtree ([R010001](requirements.md#1-restrictions-and-general-requirements)).

### Source worktree

Existing worktree selected by the user as the base for a new worktree, or as the project-file template for one.

- In [`create`](requirements.md#3-create-operation) the same source worktree is both the base for the git operation (its branch is the start point for the new branch, or its existing branch is checked out) and the template for the project file.
- In [`open`](requirements.md#4-open-operation) the picked branch supplies the git base; a separate source worktree, picked from a second quick panel, supplies only the project-file template.

In both cases, the chosen source worktree's name is recorded in [`subtree_config.json`](schemas/subtree_config.md) as `worktrees[].created_from` of the new entry.

### Orphaned project/workspace file

A `.sublime-project` or `.sublime-workspace` file in [`sublime_projects/`](structure.md) that no `worktrees[]` entry of [`subtree_config.json`](schemas/subtree_config.md) references — left behind, for example, by a hand-edited config or a worktree deleted along with its config entry but not its files. [`prune`](requirements.md#8-prune-operation) deletes orphaned files ([R080011](requirements.md#8-prune-operation)). Unlike a [stale entry](#stale-entry), an orphaned file has no config entry at all. The [main worktree](#main-worktree)'s files are always referenced and never orphaned ([R010001](requirements.md#1-restrictions-and-general-requirements)).

### Stale entry

An entry in `worktrees[]` of [`subtree_config.json`](schemas/subtree_config.md) whose [worktree directory](#worktree-directory) no longer exists on disk — a dangling reference left behind when a worktree is deleted outside Subtree. [`prune`](requirements.md#8-prune-operation) removes stale entries and their leftover project/workspace files. The [main worktree](#main-worktree) is never treated as stale ([R010001](requirements.md#1-restrictions-and-general-requirements)).

### Path rewrite

Replacement, inside a file's contents, of the [source worktree](#source-worktree)'s absolute directory path with the new worktree's absolute directory path. Only the source worktree's own path is ever replaced; paths of other worktrees are left as they are.

[`create`](requirements.md#3-create-operation) and [`open`](requirements.md#4-open-operation) perform two path rewrites that differ in how a match is recognised:

- On the new sublime-project file ([R030017](requirements.md#3-create-operation) / [R040017](requirements.md#4-open-operation)) the match is a **naive substring swap**, so a sibling path such as `worktrees/master_old` is also rewritten when the source worktree is `master` (see the [sublime project schema](schemas/sublime_project.md)).
- On every [rewritable file](#rewritable-file) in the new worktree ([R030023](requirements.md#3-create-operation) / [R040023](requirements.md#4-open-operation)) the match is **boundary-aware**, so sibling paths are left intact.

### Rewritable file

A regular (non-symlink) file in a newly created [worktree directory](#worktree-directory) that is subject to the [path rewrite](#path-rewrite) of [R030023](requirements.md#3-create-operation): it is either tracked in the worktree's git index or lies inside a directory copied per `settings.copy_directories`, and its name ends in one of the extensions listed in Subtree's source code. Files without an extension are never rewritable.

### Subtree config file

[`subtree_config.json`](schemas/subtree_config.md) at the root directory; the source of truth for Subtree's view of the repository.
