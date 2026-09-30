"""Bounds for read-only Codex review observations."""

GITHUB_API_ROOT = "https://api.github.com"
PAGE_SIZE = 100
MAX_PAGES = 20
COMMIT_PATTERN = r"[0-9a-f]{40}"
REPOSITORY_PATTERN = r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
HOLD_EXIT_CODE = 1
UNAVAILABLE_EXIT_CODE = 2
CODEX_REVIEWER_LOGIN = "chatgpt-codex-connector[bot]"
CODEX_FINDINGS_PREFIX = "Here are some automated review suggestions"
