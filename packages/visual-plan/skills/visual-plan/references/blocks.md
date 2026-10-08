# Elements and blocks

A line block takes its source as its **first child `<script type="text/plain">...</script>`**. Inside it `<` and `>` are safe. One line convention runs through the line blocks:

- `+` is good or new, `-` is bad or removed, `!` is a warning.
- A tone in square brackets at the end of an item sets its colour: `[ok]`, `[warn]`, `[bad]`, `[info]`. An item with no tone is plain.

Every item the reader can see takes a note: card titles, folds, each block, list items and question rows. You write nothing for that.

## Page elements

| Element | Attributes | Holds |
|---|---|---|
| `vp-plan` | none | the whole plan: `header`, `vp-grid`, `vp-decisions`, `vp-path`, `vp-scope` |
| `header` | none | the `h1`, and an optional `<a href>` "Full plan" link |
| `vp-grid` | `cols="Problem \| Fix \| Count"`, 2 to 4 labels | 1 to 4 `vp-band` |
| `vp-band` | `tone="ok\|warn\|bad\|info"`, `mark`, `label` | an optional `vp-card`, then `vp-row` |
| `vp-row` | none | one `vp-cell` per column |
| `vp-cell` | `face="..."` or `count="12"`, optional `id` | its card, as child content. No children: no card |
| `vp-decisions` | none | `vp-ask` |
| `vp-ask` | `id`, optional `top` | the question as the first `<p>`, then `<label><input type="radio" name value [checked]> Label</label>` options, then an optional `vp-card` |
| `vp-path` | optional `caption` | `vp-stage`, then `vp-step` |
| `vp-stage` | `label`, `state="done\|here\|next"` | its card, as child content |
| `vp-step` | `label` | its card, as child content. Steps are numbered in order |
| `vp-scope` | none | `<li>` items for the "Not changing" fold |
| `vp-card` | none | a card for a band or an ask |

A count cell shows the number and a bar scaled to the largest count in the grid. A cell id defaults to the slug of the row's first face, a dot, and the column index from 0: `clock-drift.2`. Give an `id` when two rows start with the same face.

```html
<vp-grid cols="Problem | Fix | Failures">
  <vp-band tone="warn" mark="&#8776;" label="Seen in logs">
    <vp-row>
      <vp-cell face="Port clash"> ...blocks... </vp-cell>
      <vp-cell face="Free port from the OS"> ...blocks... </vp-cell>
      <vp-cell count="7"> ...blocks... </vp-cell>
    </vp-row>
  </vp-band>
</vp-grid>
```

## Card blocks

A card is a list of blocks. Lead with a block. A card can also hold a short `<p>` and an `<h3>` section label. Other HTML goes in `vp-details`.

### `vp-flow`: what happens

One flow per line. Steps are joined by ` > `.

```html
<vp-flow><script type="text/plain">
  Test reads the wall clock > midnight passes > date check fails [bad]
  Rerun in the morning > pass [ok]
</script></vp-flow>
```

### `vp-branch`: a fork

The first line is the start flow. Each later line starts with `->` and is one outcome flow.

```html
<vp-branch><script type="text/plain">
  A test fails
  -> No retries [ok] > the log names the test
  -> Retry once [warn] > the flaky test stays
</script></vp-branch>
```

### `vp-vs`: what changes

`- flow` lines are before, `+ flow` lines are after. `before` and `after` set the row labels; the defaults are "Today" and "With the fix".

```html
<vp-vs before="Today" after="With the fix"><script type="text/plain">
  - Wall clock > date moves during the run [bad]
  + Frozen clock [info] > one date for the run [ok]
</script></vp-vs>
```

### `vp-stats`, `vp-bar`, `vp-meter`: how much

Each line is `value | label | tone`. The tone is optional.

- `vp-stats` draws number tiles. The value can be text, such as `12 / 12` or `Off`.
- `vp-bar` draws one stacked bar with a legend. The value is a number.
- `vp-meter` draws one horizontal meter per line, scaled to the largest. The value is a number. `unit=" s"` follows each value.

```html
<vp-stats><script type="text/plain">
  12 | failures in 30 days | bad
  12 / 12 | fail again on rerun | ok
</script></vp-stats>
<vp-meter unit=" runs"><script type="text/plain">
  7 | Invoices | bad
  3 | Reports | warn
</script></vp-meter>
```

### `vp-chips`: names and states

One chip per line, with an optional `[tone]`.

### `vp-checks`: what holds

`+ text` holds, `- text` fails, `! text` warns. A plain line is neutral.

```html
<vp-checks><script type="text/plain">
  + The midnight run fails before the fix
  + The midnight run passes after the fix
  ! A lint rule blocks new clock reads
</script></vp-checks>
```

### `vp-links`: which records

Each line is `label | url`, or `label | url | note`. The url is http, https, mailto or relative.

```html
<vp-links><script type="text/plain">
  Run 4417 | https://example.com/runs/4417 | due date one day off
</script></vp-links>
```

### `vp-dots`: one dot per record

Each line is `count | tone`. Use it beside a count, to show how the records split.

### `vp-ladder`: how far the evidence goes

`steps` names the rungs, split by `|`. `at` is how many rungs are filled. `small` draws it without labels.

```html
<vp-ladder steps="Said | Seen in code | Rerun fails | Fix shown" at="3" tone="ok"></vp-ladder>
```

### `vp-list`: numbered steps, valued rows or tagged facts

Each `vp-item` holds blocks. `title` puts a bold line first.

- `marks="number"` numbers the items: the parts of a fix.
- `marks="value"` puts each item's `mark` first in large type, coloured by `tone`: a row of evidence with its number.
- `marks="tag"` puts each item's `mark` first as a tag: Proof, Undo, Owner.

```html
<vp-list marks="tag">
  <vp-item mark="Proof" tone="ok"><vp-checks><script type="text/plain">+ The rerun passes</script></vp-checks></vp-item>
  <vp-item mark="Undo"><vp-flow><script type="text/plain">Revert > old behaviour</script></vp-flow></vp-item>
</vp-list>
```

### `vp-fold`: one level deeper

`summary` names what is under it. `count` and `tone` put a count badge first. `badge` puts a chip after the summary. A fold holds blocks and other folds. Opening a fold closes its open siblings.

```html
<vp-fold summary="Failures by suite" count="3" tone="bad">
  <vp-meter>...</vp-meter>
  <vp-fold summary="Invoices suite">...</vp-fold>
</vp-fold>
```

### `vp-details`: the source text

The last child of a card, at most one per card. It holds `p`, `ul`, `ol`, `table`, `pre` and `a`. It is the only place for source wording.

## What pack.mjs checks

Errors stop the write:

- an unknown `vp-` element, or one that is not closed;
- a block line that does not parse, such as a value that is not a number or an unknown tone;
- a row whose cell count differs from the column count;
- an ask with no id, a duplicate id, or a duplicate control name;
- a non-top ask without exactly one `checked` option;
- a `vp-details` that is not the last child of its card, or a second one;
- two cells with the same id;
- no `h1`, or no link to `visualplan.css` or `visualplan.js`.

Warnings are budgets for skimming: an `h1` outside 3 to 7 words, a face over 5 words, a question over 10 words, an option label over 5 words, a card `<p>` over 25 words, card text outside `vp-details` over 60 words, more than 12 grid rows, more than 10 asks, a card that starts with a paragraph, and a long dash anywhere on the page.
