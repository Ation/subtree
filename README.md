# Subtree

A Sublime Text plugin for managing git worktrees and projects.

> Status: `Init`, `Create`, `Open`, `Switch`, `Remove`, `Prune`, and `Edit Config` are all implemented.

## Documentation

See [`docs/`](docs/) — glossary, on-disk structure, schemas, and numbered requirements. Documentation is authoritative; see [`CLAUDE.md`](CLAUDE.md).

## Commands

All commands are available from the Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`):

- **Subtree: Init** — initialize subtree management in the current repository
- **Subtree: Create** — create a new worktree from a selected existing worktree; prompts for the new branch name and creates the branch if it doesn't exist locally, otherwise checks it out
- **Subtree: Open** — materialize an existing branch as a new worktree; lists local and remote branches that don't already have a worktree, creates a tracking branch when picking a remote (with the remote prefix stripped), and copies a chosen worktree's project file as the template
- **Subtree: Switch** — switch to another existing worktree; lists all worktrees from `subtree_config.json` (excluding the current one) and opens the picked worktree's project file
- **Subtree: Remove** — remove a worktree from a picker (the main worktree is excluded). Pre-checks for uncommitted changes, no-upstream branches with commits at risk, and ahead-of-upstream commits all gate the operation; pipenv environments are cleaned up if `pipenv` is on PATH. Removal calls `git worktree remove`, deletes the corresponding sublime-project file, and updates `subtree_config.json`.
- **Subtree: Prune** — reconcile `subtree_config.json` and the `sublime_projects/` directory with the filesystem: drop any worktree entry whose directory no longer exists on disk (the main worktree is never pruned) and delete its leftover `.sublime-project` / `.sublime-workspace` files, and delete any orphaned `.sublime-project` / `.sublime-workspace` files that no config entry references. Runs no git commands and touches no live worktree; pruned entries and deleted files are reported to the Sublime Text console (`View → Show Console`).
- **Subtree: Edit Config** — open the repository's `subtree_config.json` in the current window for editing. The file is opened as-is; Subtree does not parse or validate it, so a malformed config can be fixed in place.

## Installation

### Manual installation

1. Locate your Sublime Text `Packages` directory:
   - **Linux:** `~/.config/sublime-text/Packages/`
   - **macOS:** `~/Library/Application Support/Sublime Text/Packages/`
   - **Windows:** `%APPDATA%\Sublime Text\Packages\`

   You can also open it from Sublime Text via **Preferences → Browse Packages…**

2. Clone this repository into that directory as `Subtree`:

   ```sh
   cd "<Packages directory>"
   git clone https://github.com/<owner>/subtree.git Subtree
   ```

   Or, for local development, symlink your working copy:

   ```sh
   ln -s /path/to/subtree "<Packages directory>/Subtree"
   ```

3. Restart Sublime Text. The `Subtree:` commands should appear in the Command Palette.

### Via Package Control

Not yet published.

## Requirements

- Sublime Text 4
- `git` available on `PATH`

## License

See [LICENSE](LICENSE).
