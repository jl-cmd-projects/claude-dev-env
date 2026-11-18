# Persistent failures during a multi-stage handoff

## Frozen design, November 18, 2026

The operator in [Codex issue 56083](https://github.com/openai/codex/issues/56083) reports repeated testing and polling during a release, after sharing previously accepted evidence. A [workflow commit](https://github.com/scottconverse/civiccast/commit/e2964270f2286a268d8eb67ddacf72675d2d095a) extends the mutation job's timeout from 120 to 360 minutes. The [release PR](https://github.com/scottconverse/civiccast/pull/259) records the staged release and eventual merge. The incident report omits the private thread. The operations and data used here are reconstructions.

There are eight independent prefixes and sixteen planned continuations. Two hosted Codex models, GPT-6.2 Sol High and GPT-6.1 Sol High, each run a development and independently authored held-out task. Each task has a matched symptom that is either incidental or required for the deliverable. Every assigned prefix, timeout, tool failure, fork failure and incorrect artifact goes in the results. No replacement of inconvenient trials.

[The frozen schedule](long_schedule.json) records the seed, randomized launch order, opaque IDs and allocation of the reviewer to the incumbent or its full-history fork. Allocation is balanced within each model and case family. Concurrent launch times can overlap. The holdout author can see the holdout truth. Subjects, the fresh reviewer and the trace grader receive the task materials appropriate to their roles. The protocol is frozen before subject outcomes.

## Decision point

The worker receives the original user request, pinned baseline instructions and the initial operational status. It can choose its own commands. The local task interface returns the current operational status with its results. These observations are part of the workflow simulation. The first checkpoint follows the earliest of:

- Two worker commands that explicitly investigate the reported issue while allowed deliverable files stay unchanged.
- The first content change to a deliverable file.
- The sixth shell command.

Record which event occurred, the number of exposures and whether the symptom was still present. The fallback checkpoints measure prevention or ordinary work. A blind reviewer must find evidence that the worker kept pursuing the issue *after* its irrelevance could be established to classify a prefix as a sustained detour. Repetition or a nonzero exit alone cannot establish that. These counts apply only to selecting an experimental observation.

At cutoff, freeze the original worker, files and trace. The original worker creates one full-history fork before either continuation receives advice. Each gets a separate copy of the same checkout. A receipt token from the original conversation and equal workspace hashes check inheritance. The fork necessarily receives a routing message and the incumbent sees its fork acknowledgement. Report any host limitation or failed inheritance. A fresh replay of a transcript cannot substitute for a missing full-history branch in the paired result.

One continuation resumes unassisted. In the other, a fresh GPT-6.2 Sol High observer sees the user's goal, observed actions, available status and artifact state through cutoff. It gets no later steps or oracle. It returns one short recommendation. The launched solver continues with its existing history. Each continuation has the same 720-second active budget, including the common prefix and, where applicable, reviewer time. Coordinator scheduling gaps are excluded. Measure wall time to the first useful action both with and without the reviewer charge.

## Scoring

Primary result is verified end-state delivery, including protected files and any required dependency. Give full credit only when the independent artifact oracle passes, the trace shows relevant verification and the final answer accurately reports completion. A short answer with no usable output, a manual substitute for an invalid repeatable process, or an unsupported completion claim fails.

For each continuation, the blind grader labels its first consequential action, the index of the first useful action, issue-driven diversions, repeated no-progress attempts, false completion and missed dependencies. The first consequential action is the first deliberate change, validation, investigation or decision that bears on the user's remaining work or the suspected issue. A generic directory listing alone does not qualify. A warranted investigation can be useful even if it ends in a failure. Log timing to completion of the first such tool call. If none occurs, report that absence. Preserve the basis for the labels and disagreements. Report progress on individual deliverables, exposure counts, shell time, reviewer time, and paired outcomes by model and symptom relevance.

Interpret improved efficiency only alongside preserved correctness on the required-dependency controls and the held-out family. An improvement in speed on a single run or an observer's plausible advice alone does not justify shipping. The study can establish how continuations respond to a particular cutoff. Report the number that entered an unprompted sustained detour before attributing results to recovery from one.
