# PR visual

The full and core npm installs ship `pr-visual` under the shared agents home. Claude's skills pointer reads the same files. The agent interprets the PR; the bundled tools collect evidence, render visuals, and verify browser behavior.

## Exercise

1. Run `node --test packages/claude-dev-env/bin/install.pr-visual.test.mjs` to pack the npm artifact and verify full and core installs in disposable homes. The check compares installed files, checks manifest ownership and Claude's pointer, and invokes the installed renderer.
2. Run `python -m pytest packages/claude-dev-env/.agents/skills/pr-visual/scripts/test_collect.py packages/claude-dev-env/.agents/skills/pr-visual/scripts/test_render.py` for source consistency, stale-head rejection, chart provenance, invalid numbers, and hosted-payload cases.
3. From the installed skill directory, render `fixtures/flow.scene.json`, `fixtures/bar.scene.json`, `fixtures/line.scene.json`, and `fixtures/scatter.scene.json` with `scripts/render.py`.
4. Run `scripts/verify.py` on that HTML with Playwright and Chromium available. Inspect the screenshots and verification JSON for every mark, source disclosure, keyboard control, mobile panel, and widget isolation.
5. Collect an accessible PR through `scripts/collect.py`. Check the captured base, head, merge base, file count, full source, and SHA256 records before authoring a scene.

Synthetic chart fixtures prove rendering and numeric binding. Judge the agent's semantic review against the PR source separately. Collection and rendering require Python 3.11+; browser verification also requires Playwright and Chromium.
