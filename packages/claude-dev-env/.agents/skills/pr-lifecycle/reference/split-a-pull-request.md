# Split a pull request into slices

A slice is worth its own pull request when all four tests hold:

1. It merges alone and leaves the trunk working.
2. It has its own proof: a test or command that fails without the slice and passes with it.
3. It reverts alone.
4. One sentence states its purpose, and a reviewer can judge it without reading later levels. A slice that needs two sentences is usually two slices.

A cut by folder, file count, or line cap that fails these tests is cosmetic. Merge it back. Fewer slices is a valid answer, and so is one pull request with a stated reason.

Split when the change carries more than one purpose, or when one small part carries the behaviour change and its risk while the rest is library, data, or docs. Isolate the part that switches the behaviour on, so its revert is small.

Try the cheaper move first. Mark generated or data files that swell the diff with a `linguist-generated` line in `.gitattributes`, then judge the size again.

Decide the slices when you write the plan. The Delivery section of `~/.claude/docs/rule-guides/verified-work.md` already commits each verified piece as its own level. The steps below repair a pull request where that did not happen.

## Size bar

Apply the bar to each slice that passes the four tests. Count its changed lines without the generated or data files from the cheaper move above.

- About 100 lines reads well. One review holds 200 to 400 lines.
- Over 400 lines, look for another seam that passes the four tests.
- Over 1,000 lines, look harder. When no seam passes the four tests, keep the slice whole and give the stated reason under a "Why one pull request" heading.

Sources: [Google small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html) and [SmartBear code review practices](https://smartbear.com/learn/code-review/best-practices-for-peer-code-review/).

## Level order

Order levels by the import graph, as [each stack level stands on its own](../SKILL.md#each-stack-level-stands-on-its-own) and the "Sort hunks by purpose" step below describe. Two cases follow from that:

- A shared constants file is cut too, so each level carries only the constants its own code uses.
- A review rule or review doc that judges code sits at or below that code's level, so it is in force when that code is reviewed. A test or eval that imports the code stays at the code's level as that slice's proof.

## Split a pull request that is already open

1. Pin the head SHA, and stop if it moves. Build the new branches from it. Never rewrite or push to a branch another session or person owns. The owner closes the original.
2. Read the body, the open review threads, and the latest review findings, and map each open finding to the slice it lands in.
3. Sort hunks by purpose. One file can hold hunks for two slices. Check imports across each seam before you fix the order, and put foundational work at the bottom.
4. Post the plan: the slices in order, the purpose sentence and proof command for each, and the cuts that failed the tests. Then get the owner's go before you build.
5. Change no code during the split. The tree at the top of the stack equals the tree at the pinned head, so `git diff <pinned-sha> <tip> --stat` prints nothing.
6. Prove each level alone, as [each stack level stands on its own](../SKILL.md#each-stack-level-stands-on-its-own) describes. Where CI runs only on the stack tip, a lower level has no verdict until you run its checks.
7. Each new pull request links the original pull request and carries its own proof. Approvals do not carry over, so name the approvals each one still needs.
