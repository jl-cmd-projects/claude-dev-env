# Read gates

This family stops a Read before it puts too much into the context. An agent that opens a full-size screenshot spends up to 4,784 visual tokens on one image, so the gate sends it to a capped copy first.

## Checks

- `blocking/image_read_size_gate.py` denies a Read of a PNG, JPEG, GIF or WebP file whose long edge is over 512 pixels and names `scripts/agent_image_copy.py`, which writes a `<name>.agent.png` copy at 512 pixels or less with the aspect ratio kept.

## When it fires

- `blocking/image_read_size_gate.py` runs on `PreToolUse`, matcher `Read`, timeout `10` seconds in `hooks.json`. It reads only the file header, so a text file, a missing file and an unknown format pass.

## Proving it

- **Full-size screenshot.** Input is a Read of a 1440x2560 PNG. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_image_read_size_gate.py -q`. The adjacent test observes a denial that names `agent_image_copy.py`; a Read of a 288x512 copy passes.

## Gotchas

- The copy is written after the source, so a gate that wants a screenshot read after a page changed still counts the capped copy.
- A person gets the full-size file. The cap applies to what an agent reads.
