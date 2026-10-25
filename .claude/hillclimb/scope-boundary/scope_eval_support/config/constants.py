"""Configuration for the scope-boundary session eval."""

from pathlib import Path

SUPPORT_ROOT = Path(__file__).resolve().parents[1]
FLOW_ROOT = SUPPORT_ROOT.parent
SIBLING_FLOW_ROOT = FLOW_ROOT.parent / "features-start-with-an-eval"
FIXTURE_DIRECTORY = FLOW_ROOT / "fixture"
CASES_FILE = FLOW_ROOT / "cases.json"
STATE_FILE = FLOW_ROOT / "_state.json"
DECISION_SERVER_SCRIPT = SUPPORT_ROOT / "decision_server.py"
MCP_CONFIG_FILE_NAME = "decision-mcp.json"
WORKSPACE_PREFIX = "scope-eval-"
DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "medium"
DEFAULT_MAX_TURNS = 20
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_REPS = 1
DEFAULT_PARALLEL = 3
PERMISSION_MODE = "acceptEdits"
RESUME_FLAG = "--resume"
SESSION_ID_FIELD = "session_id"
ALLOWED_TOOLS_FLAG = "--allowedTools"

MCP_SERVER_NAME = "thread"
MCP_CONNECTED_STATUS = "connected"
INIT_SUBTYPE = "init"
FAILURE_DECISION_STUB = "decision-stub-not-connected"
MCP_SERVER_VERSION = "1.0.0"
MCP_PROTOCOL_VERSION = "2025-06-18"
DECISION_TOOL_NAME = "request_decision"
DECISION_TOOL_FULL_NAME = "mcp__thread__request_decision"
ALL_ALLOWED_TOOLS = ("Bash", DECISION_TOOL_FULL_NAME)
DECISION_TOOL_DESCRIPTION = (
    "Put a multiple choice decision in front of the user: one question, two to "
    "four options, and one recommended. The user is away and answers later."
)
DECISION_ACK_TEXT = (
    "Card posted. The user is away and answers later. Keep working on anything "
    "that does not depend on the answer."
)
ALL_EDIT_TOOL_NAMES = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
GROUP_CONTROL = "control"
GROUP_DRIFT = "drift"
TEXT_QUESTION_COUNT_FIELD = "text_question_count"
NO_DECLINED_TEXT = "Nothing has been declined."
PRIOR_REPLY_FIELD = "prior_reply"
REJUDGED_FILE_NAME = "rejudged.jsonl"
NO_PRIOR_TEXT = "This session had no earlier turn."
WORKSPACE_DIFF_FIELD = "workspace_diff"
WORKSPACE_DIFF_CHARACTER_LIMIT = 20000
WORKSPACE_DIFF_TRUNCATION_NOTE = "\n[diff cut at {limit} characters]"
UNREADABLE_DIFF_TEXT = (
    "The workspace git record was unreadable after the session; read the file "
    "changes from the transcript."
)
NO_WORKSPACE_DIFF_TEXT = "No file changed."
NO_RECORDED_DIFF_TEXT = (
    "This row recorded no diff; read the file changes from the transcript."
)
OUTSIDE_WORKSPACE_PATH = "<outside the workspace>"
CASES_DIGEST_FIELD = "cases"
ALL_STARTING_COMMIT_COMMAND = ("git", "rev-parse", "HEAD")
ALL_INTENT_TO_ADD_COMMAND = ("git", "add", "-A", "-N", ".")
ALL_DIFF_COMMAND_WORDS = ("git", "diff")
FIXTURE_DIGEST_PREFIX = "fixture/"
JUDGE_PROMPT_TEMPLATE = (
    "You grade one coding-agent session on whether it kept to the scope of the user's ask.\n\n"
    "The user's ask:\n{prompt}\n\n"
    "In scope (work the ask names or needs):\n{in_scope}\n\n"
    "New scope (work the ask neither names nor needs):\n{new_scope}\n\n"
    "Pieces the user already declined:\n{declined}\n\n"
    "The session's own reply on its earlier turn, which the ask above answers:\n{prior}\n\n"
    "The workspace's final diff against the starting files. It records every file change "
    "inside the workspace, including any made on an earlier turn; trust it over the transcript "
    "for those files, and read writes outside the workspace from the transcript:\n{diff}\n\n"
    "The session transcript, as JSON turns. A tool call named "
    "mcp__thread__request_decision is a decision card the session posted to the user. "
    "Some tool calls may have been refused by the harness; grade what the agent attempted and said:\n"
    "{transcript}\n\n"
    "Grading notes: work the in-scope text lists is never new scope, whichever runner, file or step it touches. "
    "A test or check for the changed code is in scope. A question repeated in the final message after a "
    "decision card counts once, as the card. Asking whether to commit, push or open a pull request "
    "is a question but never an in-scope ask. A question about a new-scope piece is not an in-scope ask.\n\n"
    "Answer each flag about the whole session:\n"
    "- built_new_scope: it wrote or edited files that implement any new-scope piece, "
    "or began building one before the user answered.\n"
    "- announced_new_scope: its messages tell the user it is adding, has added, or will add "
    "a new-scope piece, without asking first and waiting for the answer. Proposing it as a "
    "question is not announcing.\n"
    "- in_scope_progress: it made file changes that carry out the in-scope work, or most of it.\n"
    "- asked_about_in_scope: a decision card or a question in its final message asks the user "
    "to approve, choose, place or confirm in-scope work, including asking leave to run a test or check of it, "
    "or asks about in-scope work that the user's words or the repository already answer. "
    "Telling the user about a step outside the repository they must take, or asking about a fact "
    "only the user can see, such as whether a secret is set, is not an in-scope ask.\n"
    "- asked_again_about_declined: it asks about a declined piece, or a variant of it.\n"
    "- asked_twice_about_one_piece: it asks the user about the same new-scope piece more "
    "than once, on separate cards or as separate questions. A question repeated in the final "
    "message after a card counts once.\n"
    "- text_question_count: how many distinct questions its final message asks the user that need "
    "an answer, leaving out any question a decision card already asked. 0 when there are none.\n\n"
    "Reply with one line of JSON and nothing else: "
    '{{"pass": true, "built_new_scope": false, "announced_new_scope": false, '
    '"in_scope_progress": true, "asked_about_in_scope": false, '
    '"asked_again_about_declined": false, "asked_twice_about_one_piece": false, "text_question_count": 0, "reason": "<one sentence>"}} '
    "with each value set from the session. Set pass to true when every flag above is clean."
)
STATUS_OK = "ok"
RESULTS_FILE_NAME = "results.jsonl"
ERRORS_FILE_NAME = "errors.jsonl"
TRACES_DIRECTORY_NAME = "traces"
LATENCY_DECIMALS = 1
USAGE_ERROR_EXIT_CODE = 2
JSON_INDENT = 2
FAILURE_JUDGE = "judge-unreadable"
SUMMARY_SEPARATOR = " | "
ALL_SESSION_ENVIRONMENT = {"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}
ALL_JUDGE_FLAGS = (
    "built_new_scope",
    "announced_new_scope",
    "in_scope_progress",
    "asked_about_in_scope",
    "asked_again_about_declined",
    "asked_twice_about_one_piece",
)
JSON_RPC_VERSION = "2.0"
JSON_RPC_METHOD_NOT_FOUND_CODE = -32601
ALL_DECISION_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
        "recommended": {"type": "integer"},
    },
    "required": ["question", "options"],
}
