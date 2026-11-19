# pstack model configuration

feature, refactoring: gpt-6.2-sol
bug-fix: gpt-6.2-sol
perf-issue: gpt-6.2-sol
hillclimb: gpt-6.2-sol
judgment and prose: gpt-6.2-sol
strongest judgment: gpt-6.2-sol
how explorer: gpt-6-luna
how explainer: gpt-6-luna
why investigators: gpt-6-luna
why synthesizer: gpt-6-luna
reflect tooling: gpt-6.2-sol
reflect judgment, divergent, synthesizer: gpt-6.2-sol
arena runners: gpt-6.2-sol, gpt-6.2-sol, gpt-6-luna
arena cross-judge pool: gpt-6.2-sol, gpt-6.2-sol, gpt-6-luna
swarm workers: gpt-6-luna
architect runners: gpt-6.2-sol, gpt-6.2-sol, gpt-6-luna
interrogate reviewers: gpt-6.2-sol, gpt-6.2-sol, gpt-6-luna

## Reasoning effort

Single-model Luna roles use max. Sol roles use medium.
Bug-fix, judgment and prose, strongest judgment, and reflect judgment, divergent, synthesizer use xhigh.
Panel entries use xhigh, max, xhigh in the listed order.
Keep duplicate panel entries. Each entry specifies one candidate.
The cross-judge pool retains the effort paired with each entry.

Apply these substitutions once to incoming model requests:
- Sol medium through Luna max requests use gpt-6-luna with max effort.
- Sol max requests use gpt-6.2-sol with xhigh effort.
- Astra requests use gpt-6.2-sol with xhigh effort.
- Terra requests use gpt-6-luna with xhigh effort.
- Existing Luna requests use gpt-6-luna with high effort.

Explicit role and panel settings above take precedence over substitutions.
Do not apply substitutions again to their output.

session hook: on
