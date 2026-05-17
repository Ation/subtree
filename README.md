# Subtree

A Sublime Text plugin for managing git worktrees and projects.

> Status: early scaffold. The command palette entries are wired up but the commands themselves are stubs.

## Documentation

See [`docs/`](docs/) — glossary, on-disk structure, schemas, and numbered requirements. Documentation is authoritative; see [`CLAUDE.md`](CLAUDE.md).

## Commands

All commands are available from the Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`):

- **Subtree: Init** — initialize subtree management in the current repository
- **Subtree: Create** — create a new worktree
- **Subtree: Open** — open an existing worktree
- **Subtree: Remove** — remove a worktree

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
