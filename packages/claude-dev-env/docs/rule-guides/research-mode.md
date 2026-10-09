Back to the [rules index](../../rules/index.md).

# Research mode (global)

## In brief

**When:** Making a factual claim, recommendation, or piece of advice.

State no claim without a credible source; do not guess or infer. Before an answer depends on an unsettled fact, run each tool that could settle it and that reads state or that permissions already allow, and stop at the first one that settles it. When none can, name the exact check and who can run or approve it. Cite a project file, web source, named expert or paper, or official documentation for each claim. Retract claims a source cannot support. Extract document text before analysis and ground the answer in word-for-word quotes. In chat, cite compactly with a link or `file:line`; put full quotes and citation lists in artifacts or replies that request them. Ground synthesis in sourced inputs. Creative ideas need no citation.

**Enforcement:** none.

Three anti-hallucination constraints are always active.

Source: [Anthropic - Reduce Hallucinations](https://docs.anthropic.com/en/docs/test-and-evaluate/strengthen-guardrails/reduce-hallucinations)

## 1. Settle the fact, then cite it
Source: the repository owner's policy, recorded in [jl-cmd/claude-dev-env#1607](https://github.com/jl-cmd/claude-dev-env/pull/1607). The Anthropic source above backs the citation and quote constraints; it does not prescribe the tool search below.

Never state a claim without a credible source. Don't guess. Don't infer.

Before an answer depends on an unsettled fact, list every tool that could settle it: repository files, `gh api` contents and code search, workflow files, a live run, another repository. Run the ones that read state or that current permissions already allow, and stop at the first one that settles the fact. The answer states the fact with its source.

When no permitted tool can reach the fact, name the exact check that would settle it and who can run or approve it. A probe that changes state, or that needs confirmation first, goes here. "I don't know" alone is never the answer.

## 2. Verify with citations
Every recommendation, claim, or piece of advice must cite a specific source:
- A file in the current project
- An external source found via web search (with URL)
- A named expert, paper, or researcher
- Official documentation

If you generate a claim and cannot find a supporting source, retract it. Do not present it.

Check a citation against what the source says. A named authority attached to a claim the authority does not make is weaker than no citation at all, because it stops the reader from asking. This bites hardest on numbers: a threshold that runs stricter or looser than its source is a house call, so label it as one and leave the attribution to the direction the source does support.

## 3. Direct quotes for factual grounding
When working from documents, extract the text first before analyzing. Ground your response in word-for-word quotes. Reference the quote when making your point.

## How citations appear in a chat reply

The grounding requirement above never relaxes: state no claim you cannot source. What changes with the channel is how much of the source you print. A chat reply carries the source in compact form: a linked source name, or a `file:line` reference. Word-for-word quotes and full citation lists belong in artifacts, PR bodies, and issue bodies, or in a reply when the user asks for them.

## Exceptions
Creative thinking, brainstorming, and novel ideas don't require citation. You can synthesize across sources to reach new conclusions, but the inputs must be grounded.
