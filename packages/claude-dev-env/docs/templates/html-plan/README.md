# html-plan page template

Build a new artifact page from the html-plan skill. Load `house.css` from this folder after the plugin's `htmlplan.css`. The older [artifact page template](../artifact-page/README.md) stays available; use it when the request names it.

## Get the skill

The html-plan plugin is the upstream source, and it stays read-only. Keep every local change in this folder.

1. When the plugin is installed, run `/html-plan` or load the `html-plan` skill.
2. When it is not installed, clone the source read-only and read the skill from it:

   ```
   git clone --depth 1 https://github.com/anthropics/claude-plugins-community <scratch folder>
   git -C <scratch folder> checkout f60f0454df3045f724c43c6346ec80bdcc3472b2
   ```

   Read `html-plan/skills/html-plan/SKILL.md`, then `references/blocks.md` and `examples/scheduled-send.html` beside it. Link `runtime/htmlplan.css` and `runtime/htmlplan.js` from the page, and run `runtime/pack.mjs` to inline them.
3. To install the plugin, run `claude plugin install html-plan@claude-community`. The person who owns the environment approves this step.

Codex reads the same `SKILL.md` from the clone in step 2.

## House layer

`house.css` loads after `htmlplan.css`. It:

- sets the body text color and background from the theme tokens, so text keeps its contrast in dark mode,
- maps the gray text tokens to the full text color,
- sets accent and status colors that hold 7:1 contrast in light and dark,
- raises small text to 16px,
- removes opacity dimming on text.

Paste it into a `<style>` block after the plugin stylesheet, or link it beside the page.

## Check before publishing

Render the page at 390px in light and dark. Every text node is 16px or larger and holds 7:1 contrast against its painted background. The page has no console errors and no horizontal scroll.
