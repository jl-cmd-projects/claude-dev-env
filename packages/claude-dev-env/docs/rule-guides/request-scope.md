Back to the [rule entry](../../rules/request-scope.md).

# Request scope

**When this applies:** The user asks whether part of a prompt, rule, card, or check is still needed, or asks you to change one.

## Rule

Answer for the whole block that part belongs to. When a shipped hook, gate, or check now enforces what a block tells an agent to do, every line of that block that restates the enforced behavior is dead text. Propose removing all of those lines, and name each line that stays with the reason it stays.

Before you report the change done, read the output the user will use and compare it with the user's own words.

## Example

A starter's naming block holds title rules, rename steps, and steps to install a Stop hook. The user asks whether the Stop hook is still needed, and release notes show a shipped Stop gate and a title format gate.

- Narrow answer: remove the Stop hook steps and keep the rest. The title length rule and the rename steps stay, though the gates enforce both.
- Whole-block answer: remove the Stop hook steps, the rename steps, and every title rule the format gate checks. Keep the lines no gate checks, each with its reason.

**Enforcement:** none, the agent applies it.
