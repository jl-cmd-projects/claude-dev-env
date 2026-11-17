# Split a pull request into slices

A slice is worth its own pull request when all four tests hold:

1. It merges alone and leaves the trunk working.
2. It has its own proof: a test or command that fails without the slice and passes with it.
3. It reverts alone.
4. One sentence states its purpose, and a reviewer can judge it without reading later levels. A slice that needs two sentences is usually two slices.

A cut by folder, file count, or line cap that fails these tests is cosmetic, and the [size bar](#size-bar) only says when to look for a seam. Merge it back. Fewer slices is a valid answer, and so is one pull request with a stated reason.

Split when the change carries more than one purpose, or when one small part carries the behaviour change and its risk while the rest is library, data, or docs. Isolate the part that switches the behaviour on, so its revert is small.

Try the cheaper move first. Mark generated or data files that swell the diff with a `linguist-generated` line in `.gitattributes`, then judge the size again against the [size bar](#size-bar).

Decide the slices when you write the plan. The Delivery section of `~/.claude/docs/rule-guides/verified-work.md` already commits each verified piece as its own level. The steps in [Split a pull request that is already open](#split-a-pull-request-that-is-already-open) repair a pull request where that did not happen.

## Size bar

Apply the bar to each pull request, including each stack level. The bar only says when to look for a seam. Every cut still passes the four tests. Count added plus deleted lines, tests included, without lockfiles and without files marked `linguist-generated`. A renamed or moved file counts only its edited lines. Count against the merge base with the target branch, which for a stack level is the branch below it.

- Up to 400 lines fits one review, and about 100 lines reads best.
- Over 400 lines, look for a seam that passes the four tests. When none passes, keep the slice whole and state the reason in the pull request body.
- Over 1,000 lines, put that reason under a `## Why one pull request` heading.

The pull request lifecycle gate refuses a create over 1,000 changed lines against its base, with generated files and lockfiles left out. Create each stacked level with `--base` set to the branch below it, so each counts only its own lines. A body with a `## Why one pull request` heading and the reason under it passes.

Sources: [Google small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html) and [SmartBear code review practices](https://smartbear.com/learn/code-review/best-practices-for-peer-code-review/).

## Split a pull request that is already open

1. Pin the head SHA, and stop if it moves. Build the new branches from it. Never rewrite or push to a branch another session or person owns. The owner closes the original.
2. Read the body, the open review threads, and the latest review findings, and map each open finding to the slice it lands in.
3. Sort hunks by purpose. One file can hold hunks for two slices. Check imports across each seam before you fix the order, and put foundational work at the bottom.
4. Post the plan as a comment on the original pull request: the slices in order, the purpose sentence and proof command for each, and the cuts that failed the tests. Then build without waiting for a reply. The split only adds new branches, so the owner can redirect it after.
5. Change no code during the split. The tree at the top of the stack equals the tree at the pinned head, so `git diff <pinned-sha> <tip> --stat` prints nothing.
6. Prove each level alone, as [each stack level stands on its own](../SKILL.md#each-stack-level-stands-on-its-own) describes. Where CI runs only on the stack tip, a lower level has no verdict until you run its checks.
7. Each new pull request links the original pull request and carries its own proof. Approvals do not carry over, so name the approvals each one still needs.

## After a level merges

The levels above a merged level restack themselves. A workflow rebases each one onto its new base and pushes it. A level with the `status: needs-rebase` label and a restack comment needs a hand restack, so run the commands in that comment.
