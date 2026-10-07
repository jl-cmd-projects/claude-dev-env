"""Constants for the proof-in-practice check on a new pull request."""

PROOF_HEADING_PATTERN = r"^(#{1,6})[ \t]+proof in practice[ \t]*#*[ \t]*$"
NEXT_HEADING_PATTERN = r"^(#{1,6})[ \t]+\S"
COMMAND_MARKER = "`"
LINE_SEPARATOR = "\n"
ALL_GH_CREATE_WORDS = ["pr", "create"]
PULL_REQUEST_SCRIPT_NAME = "pull_request.py"
PULL_REQUEST_SCRIPT_CREATE_WORD = "create"
ALL_PYTHON_PROGRAM_NAMES = frozenset({"python", "python3", "py"})
CREATE_PULL_REQUEST_TOOL_SUFFIX = "__create_pull_request"
PROOF_GUIDE_PATH = "~/.claude/docs/rule-guides/proof-before-pull-request.md"
MISSING_BODY_REASON = (
    "Pass the pull request body with --body or --body-file so this gate can read its"
    " 'Proof in practice' section. Read " + PROOF_GUIDE_PATH + " for what counts as proof."
)
MISSING_PROOF_REASON = (
    "This pull request body has no 'Proof in practice' section with the commands you ran."
    " Before you open a pull request, run the changed thing the way its user runs it,"
    " run the same scenario without the change, and quote the output lines that show"
    " the difference. For a hook, skill, rule, setting, prompt or output style, spawn"
    " each test session through the account broker. Then add a 'Proof in practice'"
    " heading to the body that lists each command in backticks, quotes the output, states"
    " the difference between the runs, and names anything still unproven. When you cannot"
    " prove the change, leave the pull request unopened and tell the user what you could"
    " not run. Read " + PROOF_GUIDE_PATH + " for the full rule."
)
EXISTING_WORK_HEADING_PATTERN = r"^(#{1,6})[ \t]+existing work[ \t]*#*[ \t]*$"
EXISTING_WORK_GUIDE_PATH = "~/.claude/docs/rule-guides/explore-thoroughly.md"
MISSING_EXISTING_WORK_REASON = (
    "This pull request body has no 'Existing work' section. Before you open a pull"
    " request, search for what already does the change in full or in part: repository"
    " code, open and merged pull requests, hooks, rules, skills, workflows, trackers and"
    " production config. Add an 'Existing work' heading to the body. Under it, list each"
    " piece you found with its link or file:line and what this pull request adds on top"
    " of it, or state that nothing was found and name the places you searched. When the"
    " search finds a piece that already does the change, stop and report it to the user"
    " before you open the pull request. Run the search-before-acting skill and read "
    + EXISTING_WORK_GUIDE_PATH
    + " for the full rule."
)
