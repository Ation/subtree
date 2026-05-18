# Requirements

Numbered behavioural requirements, grouped by section. The R-codes are stable identifiers — reference them in commit messages and code comments.

Numbering scheme: `R<section><index>`, where `<section>` is a two-digit section number and `<index>` is a four-digit zero-padded counter within that section.

## 1. Restrictions and general requirements

- **R010001** — Subtree must not delete the [main worktree](glossary.md#main-worktree) or its corresponding sublime-project file.
- **R010002** — A [worktree directory](glossary.md#worktree-directory)'s path under `worktrees/` equals the [branch name](glossary.md#branch-name) it tracks, with `/` interpreted as a path separator. A branch named `feature/foo` resides at `worktrees/feature/foo/`.
- **R010003** — Sublime-project filenames follow `<repository_name>_<branch>.sublime-project`, with every `/` in the branch name replaced by `__` so the file sits flat under `sublime_projects/`. Example: branch `feature/foo` in repo `my_app` → `sublime_projects/my_app_feature__foo.sublime-project`.

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

- **R030001** — `create` may only run from a Sublime window that has a folder open; it operates on `window.folders()[0]`. It errors if no folder is open.
- **R030002** — `create` locates the [root directory](glossary.md#root-directory) by walking upward from the operating folder until it finds a directory containing [`subtree_config.json`](schemas/subtree_config.md). The search stops at the filesystem root.
- **R030003** — `create` aborts without modification if no `subtree_config.json` is found at or above the operating folder.
- **R030004** — `create` aborts without modification if `subtree_config.json` cannot be parsed as JSON matching the [Subtree config schema](schemas/subtree_config.md).
- **R030005** — `create` presents a quick panel listing every entry in `worktrees[].name`. The user-selected entry is the [source worktree](glossary.md#source-worktree).
- **R030006** — `create` aborts without modification if the user dismisses the quick panel.
- **R030007** — `create` aborts without modification if the source worktree's directory (`<root>/worktrees/<source-name>/`) does not exist on disk.
- **R030008** — `create` aborts without modification if the source worktree's [sublime-project file](schemas/sublime_project.md) does not exist, cannot be parsed, or its `folders` array does not contain exactly one entry. Subtree only supports single-folder source templates.
- **R030009** — After source validation, `create` prompts the user via an input panel for the new worktree's [branch name](glossary.md#branch-name).
- **R030010** — The branch name must be non-empty and must not contain `\` or control characters. `/` is allowed and is interpreted as a path separator (per [R010002](#1-restrictions-and-general-requirements)). No path segment may be empty, `.`, or `..`. The branch name is used unchanged as the worktree directory path (R010002) and, with the [R010003](#1-restrictions-and-general-requirements) substitution applied, as the project filename. This is stricter than git's own branch-name rules; git's `check-ref-format` catches any remaining invalids at operation time.
- **R030011** — `create` aborts without modification if the entered branch name duplicates an existing `worktrees[].name` entry.
- **R030012** — `create` aborts without modification if `<root>/worktrees/<branch>/` already exists on disk.
- **R030013** — `create` aborts without modification if `<root>/sublime_projects/<repository_name>_<branch>.sublime-project` already exists on disk.
- **R030014** — If the entered branch name already exists as a local git branch (resolvable from the source worktree), `create` checks it out into the new worktree via `git -C <source-worktree-dir> worktree add <root>/worktrees/<branch> <branch>`.
- **R030015** — Otherwise `create` creates a new branch from the source worktree's currently checked-out branch via `git -C <source-worktree-dir> worktree add -b <branch> <root>/worktrees/<branch> <source-branch>`.
- **R030016** — `create` aborts without modification if [R030015](#3-create-operation) would apply (new branch needed) but the source worktree has detached HEAD (no named current branch).
- **R030017** — `create` writes the new sublime-project file as a verbatim copy of the source sublime-project file, with `folders[0].path` rewritten to the absolute path of the new worktree directory. All other keys at every level are preserved as-is.
- **R030018** — `create` appends a new entry to `worktrees[]` in [`subtree_config.json`](schemas/subtree_config.md) with `name = <branch>`, `created_from = <source-worktree-name>`, and `project_file = <repository_name>_<branch>.sublime-project`. The file is rewritten with the same 4-space indent + trailing newline format `init` uses.
- **R030019** — After a successful `create`, Subtree opens the new sublime-project file and closes the originating window (mirroring [R020010](#2-init-operation)).
- **R030020** — If the `git worktree add` invocation fails, `create` surfaces git's stderr to the user and writes neither the new sublime-project file nor the config entry. Any partial directory created by git is left on disk for manual inspection.

## 4. Open operation

- **R040001** — `open` may only run from a Sublime window that has a folder open; it operates on `window.folders()[0]`. It errors if no folder is open.
- **R040002** — `open` locates the [root directory](glossary.md#root-directory) by walking upward from the operating folder until it finds a directory containing [`subtree_config.json`](schemas/subtree_config.md) (same algorithm as [R030002](#3-create-operation)).
- **R040003** — `open` aborts without modification if no `subtree_config.json` is found.
- **R040004** — `open` aborts without modification if `subtree_config.json` cannot be parsed as JSON matching the [Subtree config schema](schemas/subtree_config.md).
- **R040005** — `open` enumerates branch candidates from `refs/heads/` and `refs/remotes/` via `git for-each-ref`, skipping symref pointers (e.g. `origin/HEAD`).
- **R040006** — For a remote candidate of the form `<remote>/<rest>`, the **local name** is `<rest>` and the remote name is `<remote>`. The split is on the first `/` in the ref shortname; any further `/` segments are preserved in the local name.
- **R040007** — `open` drops from the candidate list:
  1. any candidate whose local name is already an entry in `worktrees[].name`;
  2. any remote candidate whose local name already appears under `refs/heads/` (a local ref takes precedence and is itself in the list).
- **R040008** — `open` presents a quick panel of the remaining candidates. Local entries are displayed as `<local_name>`; remote-only entries as `<local_name>  (<remote>)`.
- **R040009** — `open` aborts without modification if the user dismisses the quick panel.
- **R040010** — The picked candidate's local name must satisfy [R030010](#3-create-operation); `open` aborts without modification on failure.
- **R040011** — `open` aborts without modification if `<root>/worktrees/<local_name>/` already exists on disk.
- **R040012** — `open` aborts without modification if the computed sublime-project file path (per [R010003](#1-restrictions-and-general-requirements)) already exists on disk.
- **R040013** — `open` presents a second quick panel listing every entry in `worktrees[].name`; the user-selected entry is the **template source worktree** (a [source worktree](glossary.md#source-worktree) used only for the project file template). `open` aborts without modification if the user dismisses this panel.
- **R040014** — `open` aborts without modification if the template-source worktree's [sublime-project file](schemas/sublime_project.md) does not exist, cannot be parsed, or its `folders` array does not contain exactly one entry (mirrors [R030008](#3-create-operation)).
- **R040015** — If the picked candidate is a local branch, `open` checks it out via `git -C <main-worktree-dir> worktree add <root>/worktrees/<local_name> <local_name>`. Parent directories under `worktrees/` are created as needed.
- **R040016** — If the picked candidate is a remote-only branch, `open` creates a tracking local branch via `git -C <main-worktree-dir> worktree add -b <local_name> <root>/worktrees/<local_name> <remote>/<local_name>`. Parent directories under `worktrees/` are created as needed.
- **R040017** — `open` writes the new sublime-project file as a verbatim copy of the template-source file with `folders[0].path` rewritten to the absolute path of the new worktree directory (same rule as [R030017](#3-create-operation)).
- **R040018** — `open` appends a new entry to `worktrees[]` in [`subtree_config.json`](schemas/subtree_config.md) with `name = <local_name>`, `created_from = <template-source-name>`, and `project_file` computed per [R010003](#1-restrictions-and-general-requirements).
- **R040019** — After a successful `open`, Subtree opens the new sublime-project file and closes the originating window (mirroring [R020010](#2-init-operation) / [R030019](#3-create-operation)).
- **R040020** — If `git worktree add` fails, `open` surfaces git's stderr to the user and writes neither the new sublime-project file nor the config entry. Any partial directory created by git is left on disk for manual inspection.

## 5. Remove operation

*To be specified.*
