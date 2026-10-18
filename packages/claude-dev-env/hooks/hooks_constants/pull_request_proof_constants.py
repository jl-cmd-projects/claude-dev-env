"""Constants for the proof-in-practice check on a new pull request."""

PROOF_HEADING_PATTERN = r"^(#{1,6})[ \t]+proof in practice[ \t]*#*[ \t]*$"
NEXT_HEADING_PATTERN = r"^(#{1,6})[ \t]+\S"
COMMAND_MARKER = "`"
LINE_SEPARATOR = "\n"
ALL_GH_CREATE_WORDS = ["pr", "create"]
PULL_REQUEST_SCRIPT_NAME = "pull_request.py"
PULL_REQUEST_SCRIPT_CREATE_WORD = "create"
ALL_PYTHON_PROGRAM_NAMES = frozenset({"python", "python3", "py"})
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
INLINE_COMMAND_PATTERN = r"(?<!`)`([^`\n]+)`(?!`)"
CODE_FENCE_MARKER = "```"
FENCED_COMMAND_PROMPT = "$ "
UNITTEST_MODULE_NAME = "unittest"
PATH_WITH_LINE_PATTERN = r"^\S+:\d+(?:[-:]\d+)?$"
SINGLE_FILE_NAME_PATTERN = r"^\S*[/\\]\S*$|^[\w.-]+\.[A-Za-z0-9]+$"
ALL_PASSTHROUGH_PROGRAM_NAMES = frozenset({"tee", "tail", "head", "grep", "cat"})
ALL_TEST_RUNNER_COMMAND_PREFIXES = frozenset(
    {
        ("jest",),
        ("vitest",),
        ("mocha",),
        ("npm", "test"),
        ("npm", "t"),
        ("npm", "run", "test"),
        ("yarn", "test"),
        ("yarn", "run", "test"),
        ("pnpm", "test"),
        ("pnpm", "run", "test"),
        ("bun", "test"),
        ("npx", "jest"),
        ("npx", "vitest"),
        ("npx", "mocha"),
        ("go", "test"),
        ("cargo", "test"),
        ("deno", "test"),
        ("dotnet", "test"),
        ("unittest",),
    }
)
UNIT_TESTS_GUIDE_LINE = "Unit tests are welcome as extra evidence. The live run is the proof."
TEST_ONLY_PROOF_REASON = (
    "Every command under this pull request's 'Proof in practice' heading runs a test"
    " suite. The proof rule says: \"" + UNIT_TESTS_GUIDE_LINE + "\" Run the changed thing"
    " the way its user runs it, once without the change and once with it. List each"
    " command in backticks and quote the output lines that show the difference. Keep the"
    " test run in the section as extra evidence. Read " + PROOF_GUIDE_PATH + " for the full rule."
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
ALL_VISIBLE_FILE_SUFFIXES = (".html", ".htm", ".css", ".scss", ".tsx", ".jsx", ".vue", ".svelte")
PROOF_IMAGE_PATTERN = (
    r"!\[[^\]]*\]\([^)]+\)|https?://\S+?\.(?:png|jpe?g|gif|webp)\b"
    r"|https://claude\.ai/(?:code/)?artifact/[A-Za-z0-9-]+"
)
ALL_DEFAULT_BRANCH_REFERENCES = ("origin/HEAD", "origin/main", "main")
REMOTE_BRANCH_PREFIX = "origin/"
ALL_HEAD_FLAGS = frozenset({"--head", "-H"})
HEAD_FLAG_ASSIGNMENT_PREFIX = "--head="
ALL_BASE_FLAGS = frozenset({"--base", "-B"})
BASE_FLAG_ASSIGNMENT_PREFIX = "--base="
ALL_REPOSITORY_FLAGS = frozenset({"--repo", "-R"})
REPOSITORY_FLAG_ASSIGNMENT_PREFIX = "--repo="
GIT_TIMEOUT_SECONDS = 5
GH_TIMEOUT_SECONDS = 15
COMPARE_ENDPOINT_TEMPLATE = "repos/{repository}/compare/{base_branch}...{head_branch}"
COMPARE_FILE_NAMES_QUERY = ".files[].filename"
COMPARE_FILE_LIST_LIMIT = 300
REPOSITORY_ENDPOINT_TEMPLATE = "repos/{repository}"
DEFAULT_BRANCH_QUERY = ".default_branch"
MISSING_LOOK_REASON = (
    "This pull request changes files people see ({changed_files}), and its 'Proof in"
    " practice' section shows no picture. Render the change, open the screenshot with the"
    " Read tool and check it against the ask, then put the screenshot in the section as an"
    " image link, before and after when the change alters an existing view. Where the session"
    " cannot upload an image, publish the screenshots as an Artifact page and link it. The person who"
    " asked sees the same proof you looked at. Read " + PROOF_GUIDE_PATH + " for the full rule."
)
CHANGED_FILES_SEPARATOR = ", "
UNREADABLE_CHANGES_REASON = (
    "Neither git in this directory nor the GitHub compare API can list the files this"
    " pull request changes, so the picture check cannot tell whether people see the change."
    " Name the repository and head branch with --repo and --head, run the create call"
    " from a checkout of the head branch with origin fetched, or put a screenshot or"
    " Artifact link in the 'Proof in practice' section and run the create call again."
    " Take one of these routes now, before any change to this gate. Read "
    + PROOF_GUIDE_PATH
    + " for the full rule."
)
FEATURE_TITLE_PATTERN = r"^\s*feat(\([^)]*\))?!?:"
EVAL_HEADING_PATTERN = r"^(#{1,6})[ \t]+evals?[ \t]*#*[ \t]*$"
EVAL_GUIDE_PATH = "~/.claude/docs/rule-guides/features-start-with-an-eval.md"
MISSING_EVAL_SECTION_REASON = (
    "This feature pull request has no 'Eval' section naming its eval. A new feature is"
    " built against an eval. Invoke the Skill tool with skill 'claude-api' and args"
    " 'build-eval', build or reuse the eval it leads you to, and run it. Then add an"
    " 'Eval' heading to the body that names the eval's cases and grader, gives the"
    " command that runs it in backticks, and quotes its result. Read "
    + EVAL_GUIDE_PATH
    + " for the full rule."
)
MISSING_BUILD_EVAL_REASON = (
    "This feature pull request comes from a session that never invoked /claude-api"
    " build-eval. A new feature starts with that command. Invoke the Skill tool with"
    " skill 'claude-api' and args 'build-eval', check the eval named in the 'Eval'"
    " section with it, then run the same command again. Read "
    + EVAL_GUIDE_PATH
    + " for the full rule."
)
ALL_PROOF_GATE_DENY_MARKERS = (PROOF_GUIDE_PATH, EXISTING_WORK_GUIDE_PATH, EVAL_GUIDE_PATH)
ALL_PROOF_GATE_FILE_NAMES = frozenset(
    {
        "pull_request_proof.py",
        "pull_request_proof_constants.py",
        "pull_request_proof_edit_gate.py",
        "pre_tool_use_dispatcher_constants.py",
    }
)
GATE_EDIT_BEFORE_ROUTE_REASON = (
    "The pull request proof gate denied a create call in this session, and its deny"
    " named the way through. Take that route now. Add what the deny asked for, such as"
    " a screenshot or Artifact link in the 'Proof in practice' section, then run the"
    " create call again. The deny text is the instruction. Edit this gate only"
    " after a create call passes it. Read " + PROOF_GUIDE_PATH + " for the full rule."
)
WINDOWS_PATH_SEPARATOR = "\\"
POSIX_PATH_SEPARATOR = "/"
