# Code rules feature map

Open [the index](../CODE_RULES.md) for the rule core, then follow the family that matches the change.

- [Comment preservation](comment-preservation.md): comments, directives, and keep markers.
- [Core principles and config](core-principles-and-config.md): constants, paths, and repeated construction.
- [Lint-enforced rules](lint-enforced-rules.md): staged patterns, docstrings, imports, and logging.
- [Naming and types](naming-and-types.md): identifiers, annotations, and pytest fixtures.
- [Design and structure](design-and-structure.md): components, failure scope, and orphaned code.
- [TDD and proof](tdd-and-proof.md): tests, assertions, and review evidence.
- [Enforcement surfaces](enforcement-surfaces.md): check lanes, hook targets, and reporting.

## Feature entry contract

Each family has one agent-facing paragraph and four sections in order: Checks, When it fires, Proving it, and Gotchas. Checks lists each imported check id once across the map. Proving it names a breaking input, a pytest node or command, and an observable result for each id.

## Conventions

Keep rule headings and their short instructions in the index. Put patterns, exemptions, and procedures in the family file. Link each family back to its index section. Update the check map and its proof when the enforcer imports change.
