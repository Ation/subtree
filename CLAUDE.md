# Subtree — agent instructions

Subtree is a Sublime Text plugin for managing git worktrees and their corresponding Sublime projects in a single repository. See [`README.md`](README.md) for installation and the user-facing command list.

## Doc-first rule

Documentation under [`docs/`](docs/) is **authoritative**. Any code change must either conform to the existing docs, or update the docs in the same change. If behaviour and docs disagree, fix one of them before merging — do not leave the gap.

Requirement codes (e.g. `R020003`) defined in [`docs/requirements.md`](docs/requirements.md) are stable identifiers. Reference them in commit messages, PR descriptions, and code comments when implementing or changing related behaviour.

## Where to look

- [`docs/glossary.md`](docs/glossary.md) — terminology used throughout the project.
- [`docs/structure.md`](docs/structure.md) — on-disk layout of a Subtree-managed repository.
- [`docs/requirements.md`](docs/requirements.md) — numbered behavioural requirements, grouped by operation.
- [`docs/schemas/subtree_config.md`](docs/schemas/subtree_config.md) — schema for `subtree_config.json`.
- [`docs/schemas/sublime_project.md`](docs/schemas/sublime_project.md) — schema for the Sublime project files Subtree writes.

Read the glossary first — most other docs assume its terms.
