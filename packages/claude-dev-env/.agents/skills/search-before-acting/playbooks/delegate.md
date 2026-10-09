# Delegate

Use this playbook before you hand an ask to a worker, a thread, or another session.

1. Run the skill steps yourself before you write the brief. The worker starts from your search.
2. When a hit is full or partial, send the user the [report](../references/report-shape.md) and wait. Delegate only after the user says go.
3. Put the search result in the brief. Name each existing piece with its link or `file:line`, what it covers, and the missing part the worker builds.
4. When nothing exists, put the places searched in the brief, so the worker skips them and searches what you could not reach.
5. Ask the worker to report any existing piece it finds that the brief missed, and to stop on it before it builds.
