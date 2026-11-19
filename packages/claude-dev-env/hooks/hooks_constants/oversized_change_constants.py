"""Constants for the size check on a new pull request."""

MEASURED_LINE_BAR = 1000
SPLIT_GUIDE_PATH = "~/.claude/skills/pr-lifecycle/reference/split-a-pull-request.md"
OVERSIZED_PULL_REQUEST_REASON = (
    "This pull request changes {measured_line_count} lines against its base, over the"
    " {measured_line_bar}-line bar. Lockfiles are left out of the count, and a local count"
    " also leaves out files marked linguist-generated in .gitattributes."
    " Split it into stacked pull requests, each created with --base set to the branch below it,"
    " as " + SPLIT_GUIDE_PATH + " describes. Split first."
    " The gate passes a second create for the same branch and base. Retry the create only when"
    " no seam passes the four slice tests."
)
ATTEMPT_RECORD_FILE_TEMPLATE = "oversized-create-attempts-{session_id}.json"
ATTEMPT_RECORD_TEMPORARY_PREFIX = ".oversized-create-attempts-"
ATTEMPT_RECORD_ENCODING = "utf-8"
SESSION_ID_FIELD = "session_id"
WORKING_DIRECTORY_FIELD = "cwd"
GH_MERGE_BASE_CONFIG_KEY = "branch.{branch_name}.gh-merge-base"
HEAD_OWNER_SEPARATOR = ":"
ORIGIN_HEAD_REFERENCE = "refs/remotes/origin/HEAD"
ORIGIN_REFERENCE_PREFIX = "refs/remotes/origin/"
LINGUIST_GENERATED_ATTRIBUTE ="linguist-generated"
ALL_GENERATED_ATTRIBUTE_VALUES = frozenset({"set", "true"})
CHECK_ATTR_FIELD_COUNT = 3
ALL_LOCKFILE_NAMES = frozenset(
    {
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "bun.lockb",
        "bun.lock",
        "poetry.lock",
        "Pipfile.lock",
        "uv.lock",
        "pdm.lock",
        "Cargo.lock",
        "Gemfile.lock",
        "composer.lock",
        "go.sum",
        "flake.lock",
        "packages.lock.json",
        "Podfile.lock",
        "pubspec.lock",
        "mix.lock",
    }
)
NUMSTAT_FIELD_SEPARATOR = "\t"
NUMSTAT_FIELD_COUNT = 3
BINARY_NUMSTAT_COUNT = "-"
RENAME_DETECTION_LIMIT_OPTION = "-l1000"
COMPARE_LINE_COUNT_QUERY = (
    "(.files | length | tostring), (.files[] | [.filename, .additions, .deletions] | @json)"
)
