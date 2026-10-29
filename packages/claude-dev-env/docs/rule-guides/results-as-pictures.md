# Results as pictures

**When:** A reply reports results: a markdown table, or more figures than the reply can state without a picture.

Show the results as one chart. Render it with the pele renderer, save it as an SVG or PNG file, and pass that file in `attached_outputs`. Show every label and number on the chart. Keep the reply text to three short sentences or fewer.

## What counts as a picture

- An attached file whose name ends in `.svg`, `.png`, `.jpg`, `.jpeg`, `.gif`, or `.webp`.
- A published page attached as a `frame` output, whatever its name.
- A markdown picture outside code, such as `![Chart](chart.svg)`.
- A widget posted this turn does not count.

## Enforcement

`hooks/blocking/reply_length_gate.py` refuses a reply that reports results with no picture attached. The check reads the file name only. It does not confirm that the file exists. It does not check an edit of a posted message, because the edit tool cannot attach a file. It does not check the closing reply of a turn. `hooks/blocking/final_reply_gate.py` does not run this check.
