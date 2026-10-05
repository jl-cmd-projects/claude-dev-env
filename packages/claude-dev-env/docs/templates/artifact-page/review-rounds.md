# Marking what changed between review rounds

A page that a reviewer reads more than once shows what changed since their last look. The template marks each changed part with a thin bar on its left edge and each changed card with a small "Changed" pill. There is no diff and no list of changes.

## Data

| Field | Where | Meaning |
|---|---|---|
| `round` | top of the data block | The review round this revision answers. Add one each time the page is republished after feedback. |
| `changed_round` | an item | The round in which this item last changed. |
| `changed_parts` | an item, optional | The parts that changed: `title`, `next`, `summary`, `steps`, `links`. With no list, only the card is marked. |

When a revision answers feedback, set `round` to the new number and stamp each item it changed with that number and the parts it touched. Leave older stamps in place; they stop showing once the reviewer has seen their round.

## Behavior

- The page keeps the last round each viewer saw in `localStorage`. Parts stamped after that round are marked.
- A first visit, or a browser that blocks storage, marks the parts stamped in the current round.
- The marks hold through a reload in the same tab, through `sessionStorage`, and clear on the next visit.
- A note under the title counts the changed items and jumps to the first one.
- A changed summary opens by itself.

## Other pages

Any element with `data-changed-round="N"` takes the mark. An element that holds a `data-change-slot` child gets the "Changed" pill in that child. Other elements get the bar and a screen reader label.

The `--change` and `--change-ink` tokens hold the mark color in light and dark. Keep the pill text at 7:1 or better against `--change`.
