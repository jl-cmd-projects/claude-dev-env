"""Constants for the size check on a new pull request."""

MEASURED_LINE_BAR = 1000
REASON_LINE_CEILING = 2000
ONE_PULL_REQUEST_HEADING_PATTERN = r"^(#{1,6})[ \t]+why one pull request[?:.]?[ \t]*#*[ \t]*$"
SPLIT_GUIDE_PATH = "~/.claude/skills/pr-lifecycle/reference/split-a-pull-request.md"
OVERSIZED_PULL_REQUEST_REASON = (
    "This pull request changes {measured_line_count} lines against its base, over the"
    " {measured_line_bar}-line bar. Lockfiles are left out of the count, and a local count"
    " also leaves out files marked linguist-generated in .gitattributes."
    " Split it into stacked pull requests, each created with --base set to the branch below it,"
    " as " + SPLIT_GUIDE_PATH + " describes. When the change must stay one pull request,"
    " add a 'Why one pull request' heading to the body and state the reason under it."
)
OVER_REASON_CEILING_PULL_REQUEST_REASON = (
    "This pull request changes {measured_line_count} lines against its base, over the"
    " {reason_line_ceiling}-line ceiling that a 'Why one pull request' reason can cover."
    " Split it into stacked pull requests, each created with --base set to the branch below it,"
    " as " + SPLIT_GUIDE_PATH + " describes."
)
PARTIAL_COUNT_PULL_REQUEST_REASON = (
    "The compare API listed only its first {compare_file_list_limit} files, which change"
    " {measured_line_count} lines, so the full size is unknown. A 'Why one pull request' reason"
    " covers at most {reason_line_ceiling} lines. Fetch the base branch so git can count the"
    " whole change, then retry, or split it as " + SPLIT_GUIDE_PATH + " describes."
)
GH_MERGE_BASE_CONFIG_KEY = "branch.{branch_name}.gh-merge-base"
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
