# The Agent Merges Its Own Green Pull Request

The agent driving a pull request merges it when checks on its exact head pass, no review thread remains open, and the merge state is clean. A passing newest report permits an unstable state caused by older runs. Hold only for an owner-requested pause, requested review, or an approval rule the agent cannot satisfy. Use `agent_merge_check.py` for the verdict and repair each hold before checking again.

When this rule applies, read the full text guide before acting.

**Full text:** [`docs/rule-guides/agent-merges-its-own-green-pull-request.md`](../docs/rule-guides/agent-merges-its-own-green-pull-request.md)
