"""Patterns and payload keys for the efficient-review model gate."""

from __future__ import annotations

PYTHON_RUN_GROUP = "python_run"
EFFICIENT_REVIEW_RUN_PATTERN = (
    rf"(?<![\w.-])(?:"
    rf"(?P<{PYTHON_RUN_GROUP}>\S*(?:python\S*|py(?:\.exe)?)(?:\s+-(?!m\b)\S+)*"
    rf"\s+(?:-m\s+tools\.efficient_review|\S*tools[\\/]efficient_review\.py)"
    rf"\s+run\b)"
    rf"|gh(?:\.exe)?\s+(?:workflow\s+run|api)\b"
    r")"
)
SHELL_REPOSITORY_PATTERN = (
    r"(?:\brepos/|(?<!\S)(?:-R\s*|--repo(?:\s+|=)))[\"']?"
    r"(?P<owner>[\w.-]+)/(?P<repository>[\w.-]+)"
)
REVIEW_CONTEXT_PATTERN = r"\b(?:review|reviews)\b|\b(?:this|the|that|next)\s+run\b"
UNREADABLE_INPUT_PATTERN = (
    r"(?<!\S)(?:--json|--input)(?![\w-])"
    r"|(?<!\S)(?:-F\s*|--field(?:\s+|=))[\"']?[^\s=\"']*=@"
    r"|(?:\b|(?<=-[fF]))(?i:model)[\]\"']*\s*(?:=|:\s*)[\"']?[$%`]"
)
INVOCATION_END_PATTERN = r"(?<![\\`])\n|;|&&|\|\|?"
COMMAND_MODEL_PATTERN = (
    r"(?:\b|(?<=-[fF]))model[\]\"']*\s*(?:=|:\s*)[\"']?(?P<family>[A-Za-z][\w.-]*)"
)
DIRECTIVE_BEFORE_FAMILY_TEMPLATE = (
    r"\b(?:use|run|rerun|switch|try|pick|choose|go\s+with)"
    r"\s+(?:(?:this|that|it|the|a|an|next|efficient|review|reviews|model|on|with|in|to|for)"
    r"\s+){{0,4}}?{family}\b"
    r"(?!\s+(?:for|on|in|with)\s+"
    r"(?!(?:(?:this|the|that|next)\s+)?(?:efficient\s+)?(?:review|reviews|run|one|it)\b))"
)
HUMAN_SENDER_PATTERN = r'\bfrom=\\?"human\\?"'
CLAUSE_SPLIT_PATTERN = r"[,;:]|\bbut\b"
NEGATION_PATTERN = (
    r"\b(?:\w+n['\u2019]t|dont|cant|cannot|wont|do\s+not|never|no|not|stop)\b"
)
SENTENCE_SPLIT_PATTERN = r"(?<=[.!?])\s+|\n+"
QUESTION_END_PATTERN = r"\?\s*$"
WAKE_ENVELOPE_PATTERN = (
    r"\A\s*(?:<coordinator-relay>.*?</coordinator-relay>\s*)?"
    r"<wake\b([^>]*)>.*</wake>\s*\Z"
)
SPAWN_REASON_PATTERN = r"(?:^|\s)reason\s*=\s*[\"']spawn[\"'](?:\s|$)"
HUMAN_MESSAGE_PATTERN = (
    r"<message\b[^>]*\bfrom=\"human\"[^>]*>(?P<human_text>.*?)</message>"
    r"|<cited\b[^>]*\bauthor=\"user\"[^>]*>(?P<cited_text>.*?)</cited>"
)
RUN_WORKFLOW_METHOD = "run_workflow"
METHOD_KEY = "method"
WORKFLOW_ID_KEY = "workflow_id"
WORKFLOW_INPUTS_KEY = "inputs"
MODEL_INPUT_KEY = "model"
COMMAND_KEY = "command"
REPOSITORY_NAME_KEY = "repo"
OWNER_NAME_KEY = "owner"
RECORD_TYPE_KEY = "type"
USER_RECORD_TYPE = "user"
MESSAGE_KEY = "message"
CONTENT_KEY = "content"
SOURCE_TOOL_USE_ID_KEY = "sourceToolUseID"
IS_META_RECORD_KEY = "isMeta"
TEXT_BLOCK_TYPE = "text"
TOOL_REPLY_BLOCK_TYPE = "tool_result"
BLOCK_TYPE_KEY = "type"
TEXT_KEY = "text"
TRANSCRIPT_ENCODING = "utf-8"
TRANSCRIPT_DECODE_ERRORS = "replace"
TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
TRANSCRIPT_PATH_KEY = "transcript_path"
REVIEW_MODEL_FAMILY = "haiku"
HOOK_EVENT_NAME = "PreToolUse"
ALTERNATION_SEPARATOR = "|"
TARGET_BOUNDARY_TEMPLATE = r"(?<![\w.-])(?:{joined})(?![\w.-])"
RECORD_LINE_SEPARATOR = "\n"
