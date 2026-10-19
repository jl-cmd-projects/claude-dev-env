# Choose the format from the question

| Question | Format | Required evidence |
| --- | --- | --- |
| What executes, and when? | Flow or decision diagram | Entry points, branches, outputs |
| What depends on what? | Architecture or dependency graph | Calls, ownership, contracts; label arrows |
| What changes between versions? | Before/after lanes or comparison | Both captured revisions |
| How do categories differ? | Bar chart | Numeric JSON observations with units |
| How does a measurement change over ordered observations? | Line chart | Numeric x and y; disclose missing intervals |
| Do two measurements move together? | Scatter plot | Paired numeric x and y; no causal claim |

Charts and graphs answer different questions. Use the code graph for behavior; use a data chart for measured quantities. A PR's claim that it is faster does not supply benchmark data. If captured measurements are absent, explain the behavior change and state the measurement gap.

Every chart mark remains selectable, with the same visual drilldown and collapsed source evidence as a flow node. Use separate scenes for behavior and measurements when both help. Keep synthetic examples labeled as synthetic. Never infer runtime, quality, or business improvements from changed line counts.
