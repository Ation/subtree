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
- **R020004** — When invoked from a Sublime window, `init` operates on the first folder opened in that window (`window.folders()[0]`). It errors if no folder is open.
- **R020005** — `init` prompts the user for the [repository name](glossary.md#repository-name) via an input panel pre-filled with the target directory's basename. The user may accept or modify the value.
- **R020006** — The [repository name](glossary.md#repository-name) must be non-empty and must not contain `/`, `\`, or control characters; it is used as a filename component.
- **R020007** — `init` aborts without modification if [`subtree_config.json`](schemas/subtree_config.md) already exists at the target.
- **R020008** — `init` aborts without modification if `worktrees/` or `sublime_projects/` already exists at the target (reserved-name collision).
- **R020009** — `init` aborts without modification if HEAD is detached (no current branch name). The user must check out a branch before running `init`.
- **R020010** — After successful `init`, Subtree opens the newly created [sublime-project file](schemas/sublime_project.md) and closes the originating window.

## 3. Create operation

*To be specified.*

## 4. Open operation

*To be specified.*

## 5. Remove operation

*To be specified.*
