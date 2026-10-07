# Drive a mod in a pseudo-terminal

A cloud session can run Claude Code with a mod loaded, press keys, click, hover, and capture the screen,
with no PC and no person. Use the mod repository's own driver when it ships one. Build on the same parts
when it does not.

## The parts

| Part | Job |
| --- | --- |
| `node-pty` | Runs `claude --plugin-dir <mod>` in a pseudo-terminal. |
| `@xterm/headless` | Mirrors the output into a cell buffer, so the screen reads as text with colors. |
| A local mock of the Messages API | Scripts each model turn, so the model calls the tool that fires the mod. Point `ANTHROPIC_BASE_URL` at it. |
| A throwaway home and config folder | Seeds onboarding, API key approval and folder trust, so the first screen is the prompt. |
| A renderer | Paints the cells to HTML and screenshots it with Playwright Chromium, so the capture is a PNG. |

## Input bytes

| Action | Bytes written to the terminal |
| --- | --- |
| Enter | `\r` |
| Tab, Shift+Tab | `\t`, `\x1b[Z` |
| Escape | `\x1b` |
| Arrow up, down, right, left | `\x1b[A`, `\x1b[B`, `\x1b[C`, `\x1b[D` |
| Clear the prompt line | `\x15` |
| Left click at column `c`, row `r` (1-based) | `\x1b[<0;c;rM` then `\x1b[<0;c;rm` |
| Hover at column `c`, row `r` | `\x1b[<35;c;rM` |

Find `c` and `r` by searching the cell buffer for the text to point at. Search from the bottom row up,
so a click lands on the newest copy of a label. Skip zero-width cells when you join a row, or wide
characters shift every column after them.

## The loop

1. Write the steps: the scripted turns, then each key, click or hover, the text to wait for, and a capture.
2. Run them. Wait for each step's text, then for the screen to stop changing, before the next step.
3. Read the text capture for words, and open the PNG for color and layout.
4. Fix the mod, run again, and keep the passing captures as the proof.

## Gotchas

- A tool the scripted turn calls needs `--allowedTools <tool>`, or a permission prompt stops the run.
- Check the request body for your tool id, so the second request ends the turn with text.
- A mod can refuse to draw a pane below a minimum width. Run at 180 columns unless the steps need less.
- A toast draws in the top-right corner, over the header rows.
- A PNG renderer can paint a wide emoji over the next cell. The text capture holds the characters as drawn.
- A step that runs a script from the project folder fails in the sandbox, because that folder is empty.
