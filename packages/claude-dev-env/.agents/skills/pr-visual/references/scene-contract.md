# Scene contract

The scene is the agent's source-backed interpretation. The renderer checks evidence locations and edge endpoints; it does not judge whether the prose correctly explains the code. Inspect that separately.

Each scene is a JSON object with these fields.

| Field | Value |
| --- | --- |
| `snapshot` | Relative path from scene file to collector snapshot.json. |
| `tab` | Short topic name for the gallery tab. |
| `title` | Diagram headline, under 50 characters. |
| `subtitle` | One sentence describing the change. |
| `before`, `after` | Short statements beginning BEFORE and AFTER. |
| `alt` | Text description of the flow and branches. |
| `groups` | Optional array of `{x,y,w,h,label}` frames. |
| `nodes` | Positioned semantic nodes, specified below. |
| `edges` | Routed connectors, specified below. |
| `notes` | Three objects with `label` and two short `text` lines. |
| `comparison` | Paragraph strings comparing the captured summary with the code. |
| `review` | Paragraph strings stating review scope, supported concerns, and evidence limitations. |

Each node contains `id`, `x`, `y`, `label` as an array of short lines, `icon`, `kind`, `detail` as paragraph strings, and nonempty `sources`. Optional `sub` is an array of short secondary lines. Available icons are the symbol IDs in `assets/icons.symbols`. Kinds are `blue`, `green`, `lime`, `orange`, the empty string, or `decision`.

Each source contains `path`, one-based `line`, optional inclusive `end`, and optional `side`, either `head` or `base`. Source lines come from captured files. Store additional unchanged caller source in the snapshot's matching side directory. Record its retrieval and hash when adding it. The renderer derives immutable GitHub links and embeds the excerpt. Never put raw HTML in a label or detail.

Every node also needs a `drilldown` object with a `title` and two to six `steps`. Each step has `label` as an array of short lines, `icon` from the icon symbols, and optional `kind`. The labels explain the mechanism supported by that node's sources. The renderer lays out the steps in a three-column snake. By default it connects consecutive steps. Optional `edges` can replace that sequence with explicit zero-based `from` and `to` indices, optional `kind`, and an optional short `label`. Do not connect alternative outcomes as if both execute in sequence. Related-step buttons come from neighboring nodes in the main graph.

The panel shows the drilldown first. Its `detail` paragraphs and `sources` remain in a collapsed disclosure. Changing nodes resets that disclosure. Mini-diagram wording is authored interpretation and needs the same source review as the main diagram.

Each edge contains `from`, `to`, `path`, and `kind`. Use SVG path coordinates for `path`. Kinds are `green`, `orange`, `dotted`, or the empty string. Optional `label` needs `x` and `y` for its position. Draw connections to the edge of each node shape. A dotted connector can show a supporting measurement or a repeat schedule. Label that relationship so it cannot imply execution ordering.

See `fixtures/*.scene.json` for synthetic flow and chart instances. Write a fresh scene when the PR changes.

## Charts

Add `chart: {"kind": "bar", "x_label": "Sample", "y_label": "Duration (ms)"}`. Supported kinds are `bar`, `line`, and `scatter`. Keep `edges` empty unless a separate code relationship needs related-node navigation. Chart nodes use the same evidence and drilldowns; their layout coordinates are ignored.

Each chart node has `metrics.y: {"source": 0, "pointer": "/samples/0/duration_ms"}`. The source index refers to that node's `sources` array. The pointer resolves a number from the captured JSON file. Line and scatter nodes also require `metrics.x`. Author-entered coordinates, booleans, missing values, NaN, and infinity are rejected. Missing values must be disclosed and omitted, never filled with zero. Bar charts include zero; line points sort by numeric x. Do not connect across a known missing interval: use scatter or separate scenes. Units belong in axis labels. Keep a chart to a readable number of points; use separate scenes for different series.
