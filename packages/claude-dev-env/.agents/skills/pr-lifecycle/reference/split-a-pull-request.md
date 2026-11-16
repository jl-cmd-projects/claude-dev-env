# Split a pull request into slices

A slice is worth its own pull request when all four tests hold:

1. It merges alone and leaves the trunk working.
2. It has its own proof: a test or command that fails without the slice and passes with it.
3. It reverts alone.
4. One sentence states its purpose, and a reviewer can judge it without reading later levels. A slice that needs two sentences is usually two slices.

A cut by folder, file count, or line cap that fails these tests is cosmetic. Merge it back. Fewer slices is a valid answer, and so is one pull request with a stated reason.

Split when the change carries more than one purpose, or when one small part carries the behaviour change and its risk while the rest is library, data, or docs. Isolate the part that switches the behaviour on, so its revert is small.

Try the cheaper move first. Mark generated or data files that swell the diff with a `linguist-generated` line in `.gitattributes`, then judge the size again.

## Size bar

Check size after the four tests pass. Count changed lines and leave out generated files.

- About 100 lines reads well. One review holds 200 to 400 lines.
- Over 400 lines, look for another seam that passes the four tests.
- Over 1,000 lines, split, or state in a "Why one pull request" section why the slice stays whole.

The pull request lifecycle gate refuses a create over 1,000 changed lines against its base, with generated files and lockfiles left out. Create each stacked level with `--base` set to the branch below it, so each counts only its own lines. A body with a `Why one pull request` heading and the reason under it passes.

A cut that meets the bar and fails the tests is still cosmetic. Sources: [Google small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html) and [SmartBear code review practices](https://smartbear.com/learn/code-review/best-practices-for-peer-code-review/).

## Level order

Order levels by the import graph, as [each stack level stands on its own](../SKILL.md#each-stack-level-stands-on-its-own) and step 3 below describe. Two more rules:

- Cut a shared constants file so each constant lands at the level of its first user.
- A check, eval, or review rule sits at or below the level of the code it judges, so it is in force when that code is reviewed.

Decide the slices when you write the plan. The Delivery section of `~/.claude/docs/rule-guides/verified-work.md` already commits each verified piece as its own level. The steps below repair a pull request where that did not happen.

## Split a pull request that is already open

1. Pin the head SHA, and stop if it moves. Build the new branches from it. Never rewrite or push to a branch another session or person owns. The owner closes the original.
2. Read the body, the open review threads, and the latest review findings, and map each open finding to the slice it lands in.
3. Sort hunks by purpose. One file can hold hunks for two slices. Check imports across each seam before you fix the order, and put foundational work at the bottom.
4. Post the plan: the slices in order, the purpose sentence and proof command for each, and the cuts that failed the tests. Then get the owner's go before you build.
5. Change no code during the split. The tree at the top of the stack equals the tree at the pinned head, so `git diff <pinned-sha> <tip> --stat` prints nothing.
6. Prove each level alone, as [each stack level stands on its own](../SKILL.md#each-stack-level-stands-on-its-own) describes. Where CI runs only on the stack tip, a lower level has no verdict until you run its checks.
7. Each new pull request links the original pull request and carries its own proof. Approvals do not carry over, so name the approvals each one still needs.
