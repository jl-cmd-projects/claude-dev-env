# Filesystem search

**When:** Searching for files by name, path, extension, size, or date.

Scope every search to a project, worktree, package, or narrowing filter. Never start at a filesystem root, drive root, bare home, or share root. Read a known path directly; use scoped `es.exe`, Glob, or Grep for discovery. After `es.exe` Error 8, retry twice before falling back within the same scope. Run one large shell walk at a time.

**Enforcement:** none.

**Full text:** [guide](../docs/rule-guides/filesystem-search.md). Read it for tool selection and search examples.
