# Prefer existing tools

Full text behind [`rules/prefer-existing-tools.md`](../../rules/prefer-existing-tools.md), which loads in sessions as the short form.

## What a candidate must cover

Internal code includes the repository and its shared packages. An established external option has a security process, a field reputation, broad use measured by stars, downloads, or dependents, and maintenance shown by a release or commit within the last year. An open critical advisory rules it out.

Custom rules belong in the chosen tool's configuration format. A wrapper adds code that this package must maintain.

The choice report identifies the tool by name and link, gives its license, and cites one adoption count. A custom build's report records the candidates and the missing capability that ruled out each one.

## Why this rule exists

Code written here needs local maintenance. A widely used tool draws fixes and new patterns from its maintainers and users.

## Sibling rules

| Rule | Role |
|---|---|
| [`explore-thoroughly.md`](explore-thoroughly.md) | Read existing code before proposing a change |
| [`verify-before-asking.md`](verify-before-asking.md) | Check a question with a tool before asking it |
