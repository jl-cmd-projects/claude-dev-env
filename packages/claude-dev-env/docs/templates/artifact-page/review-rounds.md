# Marking what changed between review rounds

A page that a reviewer reads more than once shows what changed since their last look. The template marks only the parts that changed: each one gets a thin bar on its left edge and a small "Changed" label at its start. The card around them stays as it is, and its board chip gets a dot in the same color. There is no diff and no list of changes.

## Data

| Field | Where | Meaning |
|---|---|---|
| `round` | top of the data block | The review round this revision answers. Add one each time the page is republished after feedback. |
| `changed_round` | an item | The round in which this item last changed. |
| `changed_parts` | an item | The parts that changed: `title`, `next`, `summary`, `steps`, `links`. An item with no list gets no mark. |

When a revision answers feedback, set `round` to the new number and stamp each item it changed with that number and the parts it touched. Leave older stamps in place; they stop showing once the reviewer has seen their round.

## Behavior

- The page keeps the last round each viewer saw in `localStorage`. Parts stamped after that round are marked.
- A first visit, or a browser that blocks storage, marks the parts stamped in the current round.
- The marks hold through a reload in the same tab, through `sessionStorage`, and clear on the next visit.
- A changed summary opens by itself.

## Other pages

Stamp the smallest element that changed with `data-changed-round="N"`; it takes the bar and the "Changed" label, and a `<details>` element takes the label in its summary. Never stamp a whole card or section. An element with `data-change-mark="dot"` takes the dot and a screen reader label in place of the bar and label.

The `--change` and `--change-ink` tokens hold the mark colors in light and dark. Keep the label text at 7:1 or better against `--change`, and the bar at 3:1 or better against `--surface` and `--bg`.
