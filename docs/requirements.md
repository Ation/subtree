# Requirements

Numbered behavioural requirements, grouped by section. The R-codes are stable identifiers — reference them in commit messages and code comments.

Numbering scheme: `R<section><index>`, where `<section>` is a two-digit section number and `<index>` is a four-digit zero-padded counter within that section.

## 1. Restrictions and general requirements

- **R010001** — Subtree must not delete the [main worktree](glossary.md#main-worktree) or its corresponding sublime-project file.
- **R010002** — A [worktree directory](glossary.md#worktree-directory)'s name must equal the [branch name](glossary.md#branch-name) it tracks.

## 2. Init operation

- **R020001** — `init` may only run from a directory that contains a `.git` directory (i.e. a regular git working tree).
- **R020002** — The currently checked-out branch is recorded as the main worktree's branch in [`subtree_config.json`](schemas/subtree_config.md) under `meta_information.main_worktree`.
- **R020003** — `init` converts the current directory into the [root directory](glossary.md#root-directory) by performing all of the following:
  1. Create `sublime_projects/` and `worktrees/`.
  2. Create the main worktree directory at `worktrees/<current-branch>/`.
  3. Move all existing repository contents (including `.git`) into that directory.
  4. Write [`subtree_config.json`](schemas/subtree_config.md) at the root.
  5. Create the initial sublime-project file at `sublime_projects/<repository_name>_<current-branch>.sublime-project` (see [Sublime project schema](schemas/sublime_project.md)).

## 3. Create operation

*To be specified.*

## 4. Open operation

*To be specified.*

## 5. Remove operation

*To be specified.*
