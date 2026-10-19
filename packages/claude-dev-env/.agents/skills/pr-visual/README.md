# PR visual

A portable agent skill with Python tools. The agent reviews the PR summary and code, authors a source-backed scene, and returns an interactive HTML visual. Claude Code, Codex, and other agents can follow SKILL.md; no model API is embedded.

Requires Python 3.11+, authenticated GitHub CLI for collection, and Playwright plus Chromium for browser verification. Collection and rendering use the standard library. Optional browser setup: `python -m pip install playwright`, then `python -m playwright install chromium`.

```sh
python scripts/collect.py https://github.com/OWNER/REPO/pull/NUMBER --out RUN/evidence
python scripts/render.py SCENE.json --out RUN/visual.html --links-only
python scripts/verify.py RUN/visual.html --out RUN/proof
```

Flow diagrams, decision trees, dependency graphs, comparisons, bar charts, line charts, and scatter plots share the same source details. Numerical chart coordinates resolve JSON pointers against captured source files. The renderer does not supply an independent semantic code review.

Try the synthetic fixture gallery from this directory:

```sh
python scripts/render.py fixtures/flow.scene.json fixtures/bar.scene.json fixtures/line.scene.json fixtures/scatter.scene.json --out /tmp/pr-visual.html
python scripts/verify.py /tmp/pr-visual.html --out /tmp/pr-visual-proof
python -m pytest scripts/test_render.py
```

Add `--browser-path PATH` when Chromium is outside the usual locations. `--no-sandbox` is available for isolated containers that cannot run Chromium's sandbox. Private evidence and generated HTML belong outside the skill package.

The npm installer ships this skill through `.agents/skills` in full and core installs. Claude's skills directory points to the same installed agent skill tree. Release automation publishes the npm package after merge.

When Data is available, the skill can use its chart-selection and quantitative-review workflow and plan integrated visuals for distributions, heatmaps, composition, and uncertainty. These additional families require that workflow's supported renderer.

Reviews start with compact PR selectors. Charts live inside relevant flow-step cards and their expansions. Render `fixtures/integrated.scene.json` to exercise that layout. Source examples can read numeric Python literals without executing the PR.
