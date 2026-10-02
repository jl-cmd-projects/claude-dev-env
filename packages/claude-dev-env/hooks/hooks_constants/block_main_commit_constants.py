"""Constants for the protected-branch commit gate."""

PULL_REQUEST_INSTRUCTION = (
    " Instead: (1) create a feature branch with `git checkout -b <descriptive-branch-name>`, "
    "(2) commit your changes there, "
    "(3) push with `git push -u origin <branch-name>`, "
    "(4) open a pull request with `gh pr create`. "
    "If you must commit to main, the user needs to approve explicitly."
)
