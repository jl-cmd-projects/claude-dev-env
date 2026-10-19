# Choose the format from the question

| Question | Format | Required evidence |
| --- | --- | --- |
| What executes, and when? | Flow or decision diagram | Entry points, branches, outputs |
| What depends on what? | Architecture or dependency graph | Calls, ownership, contracts; label arrows |
| What changes between versions? | Before/after lanes or comparison | Both captured revisions |
| How do categories differ? | Bar chart | Numeric observations or source examples with units |
| How does a measurement change over ordered observations? | Line chart | Numeric x and y; disclose missing intervals |
| Do two measurements move together? | Scatter plot | Paired numeric x and y; no causal claim |

Charts and graphs answer different questions. Use the code graph for behavior; use a data chart for measured quantities. A PR's claim that it is faster does not supply benchmark data. If captured measurements are absent, explain the behavior change and state the measurement gap.

Full-scene chart marks remain selectable. Contextual charts belong inside the flow-step cards and expansions they explain. Keep the top dashboard free of plots. Show compact chart glances within the flow and fuller charts in the selected step expansion. Keep synthetic examples labeled as synthetic. Never infer runtime, quality, or business improvements from changed line counts.

## Data integration

When Data is available, read its `visualize-data` skill before planning a quantitative visual. Supply reviewed observations, immutable PR source links, units, observation grain, population, period, and available denominators. Keep the PR review and its code evidence in this skill's workflow. Follow Data's selected-surface rendering and verification requirements. Embed supported output into the relevant review card or detail panel. Keep one Page and one integrated review experience.

| Analytical question | Additional family to consider | Delivery |
| --- | --- | --- |
| How are observations distributed? | Histogram or box plot | Integrated Data visual |
| How does a cohort or matrix vary? | Heatmap | Integrated Data visual |
| What contributes to an additive change? | Waterfall | Integrated Data visual |
| What share belongs to each exclusive category? | Stacked bars | Integrated Data visual |
| What is the estimate and its uncertainty? | Points with intervals or line with a band | Integrated Data visual |

The bundled scene renderer accepts bar, line, and scatter charts. Other families use a separately supported renderer; never label an unsupported scene as rendered. If Data or the required surface is unavailable, return the supported PR visual and explain the missing chart capability.

Use comparable observations at one grain for scatter plots. Preserve denominators and sample sizes when they affect interpretation. Keep scales consistent across magnitude comparisons. For sparse ordered data, consider bars or a table. Preserve reviewed uncertainty with the estimate; use a supported embedded chart or an estimate-and-bounds table when the bundled renderer cannot show it. Avoid summing overlapping categories or averaging rates without their denominators.
