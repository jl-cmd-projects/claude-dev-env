"""Constants for the size check on a new pull request."""

import re

MEASURED_LINE_BAR = 1000
SPLIT_GUIDE_PATH = "~/.claude/skills/pr-lifecycle/reference/split-a-pull-request.md"
OVERSIZED_PULL_REQUEST_REASON = (
    "This pull request changes {measured_line_count} lines against its base, over the"
    " {measured_line_bar}-line bar. Lockfiles are left out of the count, and a local count"
    " also leaves out files marked linguist-generated in .gitattributes."
    " Split it into stacked pull requests, each created with --base set to the branch below it,"
    " as " + SPLIT_GUIDE_PATH + " describes. Split first."
    " The gate passes a second create for the same branch and base, and a create after the user"
    " says in this session that this one stays one pull request. Retry the create only when no"
    " seam passes the four slice tests."
)
ATTEMPT_RECORD_FILE_TEMPLATE = "oversized-create-attempts-{session_id}.json"
ATTEMPT_RECORD_TEMPORARY_PREFIX = ".oversized-create-attempts-"
ATTEMPT_RECORD_ENCODING = "utf-8"
SESSION_ID_FIELD = "session_id"
TRANSCRIPT_PATH_FIELD = "transcript_path"
WORKING_DIRECTORY_FIELD = "cwd"
GH_MERGE_BASE_CONFIG_KEY = "branch.{branch_name}.gh-merge-base"
HEAD_OWNER_SEPARATOR = ":"
LINGUIST_GENERATED_ATTRIBUTE = "linguist-generated"
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
USER_ROLE = "user"
RECORD_TYPE_KEY = "type"
MESSAGE_KEY = "message"
ROLE_KEY = "role"
CONTENT_KEY = "content"
TEXT_KEY = "text"
TEXT_BLOCK_TYPE = "text"
TOOL_RESULT_BLOCK_TYPE = "tool_result"
ALL_SKIPPED_RECORD_FLAGS = ("isCompactSummary", "isSidechain")
META_RECORD_FLAG = "isMeta"
ORIGIN_KEY = "origin"
ORIGIN_KIND_KEY = "kind"
ALL_TYPED_ORIGIN_KINDS = (None, "human")
ALL_RELAY_ORIGIN_KINDS = (None, "task-notification")
RELAY_WRAPPER_PATTERN = re.compile(r"<(?:coordinator-)?relay\b")
CITED_USER_TEXT_PATTERN = re.compile(r"<cited\b[^>]*\bauthor=\"user\"[^>]*>(.*?)</cited>", re.DOTALL)
LEADING_TAG_PATTERN = re.compile(r"\s*<[a-z]")
SENTENCE_BREAK_PATTERN = re.compile(r"(?<=[.!?])\s+|\n+")
QUESTION_MARK = "?"
CURLY_APOSTROPHE = "’"
STRAIGHT_APOSTROPHE = "'"
KEEP_WHOLE_PATTERN = re.compile(
    r"\b(?:do not|don't|dont|no need to)\s+split\s+"
    r"(?:it|(?:this|that|the)(?:\s+(?:one|pr|pull request))?)(?!\s+\w)"
)
SPLIT_WORD_PATTERN = re.compile(r"\bsplit")
NEGATION_PATTERN = re.compile(r"n't\b|\b(?:not|no|never|dont|cannot)\b")
RULE_TALK_PATTERN = re.compile(
    r"\b(?:if|whether|unless|until|gate|rule|but|yet|said|depends?)\b"
)
APPROVAL_PATTERN = re.compile(
    r"\b(?:approve[ds]?|approving|approval|fine|ok|okay|go ahead|open it|ship it"
    r"|(?:keep|leave|stays?)\s+(?:it\s+|this\s+|that\s+)?(?:as\s+)?(?:a\s+)?(?:one|single))\b"
)
SIZE_SUBJECT_PATTERN = re.compile(
    r"\b(?:(?:one|single)\s+(?:pr|pull request)|size bar|oversized"
    r"|size\b.*\b(?:pr|pull request)|(?:pr|pull request)\b.*\bsize)\b"
)
