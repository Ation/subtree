# Sublime project file schema

Subtree writes one `.sublime-project` file per worktree, stored under `sublime_projects/` and named `<repository_name>_<branch>.sublime-project` (see [structure](../structure.md)).

## Initial structure

When created, the file contains a single folder entry pointing at the [worktree directory](../glossary.md#worktree-directory):

```json
{
    "folders": [
        { "path": "<absolute path to worktree directory>" }
    ]
}
```

## Notes

- Subtree writes **absolute** paths in `folders[].path` so the project file is independent of where Sublime Text is launched from. Sublime also accepts relative paths, but Subtree does not use them.
- After creation, the file may be edited freely by the user (additional folders, build systems, settings, etc.). Subtree does not rewrite a project file's contents beyond what is specified here unless a future requirement explicitly says otherwise.
