"""Constants for the verify-before-commit gate."""

DENY_REASON = (
    "This repository has a verify skill, and this commit changes code. Invoke the verify "
    "skill with the Skill tool, run the check it routes you to, then run the same command again. "
    "A commit that changes only docs, data files under a docs folder, or tests passes without it."
)
SKILL_NAME = "verify"
ALL_SLASH_COMMAND_MARKERS = ("<command-name>/verify</command-name>",)
ALL_VERIFY_SKILL_DIRECTORIES = (".claude/skills/verify", ".agents/skills/verify")
COMMIT_ACTION = "commit"
ADD_ACTION = "add"
ALL_GIT_EXECUTABLES = frozenset({"git", "git.exe"})
GIT_DIRECTORY_OPTION = "-C"
ALL_COMMIT_ALL_OPTIONS = frozenset({"-a", "--all"})
COMMIT_ALL_SHORT_FLAG = "a"
ALL_COMMIT_VALUED_SHORT_FLAGS = frozenset("mFCct")
ALL_ADD_EVERYTHING_OPTIONS = frozenset({"-A", "--all", "-u", "--update"})
WHOLE_TREE_PATHSPEC = ":/"
PATHSPEC_TERMINATOR = "--"
GIT_TIMEOUT_SECONDS = 5
ALL_TOP_LEVEL_ARGUMENTS = ("rev-parse", "--show-toplevel")
ALL_STAGED_PATHS_ARGUMENTS = ("diff", "--cached", "--name-only")
ALL_TRACKED_CHANGE_ARGUMENTS = ("diff", "--name-only")
ALL_PATHSPEC_CHANGE_ARGUMENTS = ("diff", "--name-only", "HEAD", "--")
ALL_COMMIT_INCLUDE_OPTIONS = frozenset({"-i", "--include"})
ALL_COMMIT_VALUED_LONG_OPTIONS = frozenset(
    {
        "--author",
        "--cleanup",
        "--date",
        "--file",
        "--fixup",
        "--message",
        "--pathspec-from-file",
        "--reedit-message",
        "--reuse-message",
        "--squash",
        "--template",
        "--trailer",
    }
)
ALL_DIRECTORY_CHANGE_COMMANDS = frozenset(
    {"cd", "chdir", "pushd", "set-location", "sl", "push-location"}
)
ALL_DIRECTORY_CHANGE_VALUED_OPTIONS = frozenset({"-path", "-literalpath"})
PREVIOUS_DIRECTORY_ARGUMENT = "-"
ALL_UNEXPANDED_PATH_MARKS = ("$", "`", "%")
ALL_WORKING_TREE_PATHS_ARGUMENTS = (
    "ls-files",
    "--modified",
    "--others",
    "--deleted",
    "--exclude-standard",
    "--full-name",
    "--",
)
ALL_DOCS_EXTENSIONS = frozenset(
    {
        ".md",
        ".mdx",
        ".txt",
        ".rst",
        ".adoc",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".webp",
        ".ico",
    }
)
ALL_DOCS_DIRECTORY_NAMES = frozenset({"docs"})
ALL_DOCS_DATA_EXTENSIONS = frozenset({".json", ".jsonl", ".yaml", ".yml", ".csv"})
ALL_TEST_DIRECTORY_NAMES = frozenset({"tests", "test", "__tests__"})
ALL_TEST_FILE_PREFIXES = ("test_",)
ALL_TEST_FILE_SUFFIXES = ("_test.py",)
ALL_TEST_FILE_INFIXES = (".test.", ".spec.")
ALL_TEST_FILE_NAMES = frozenset({"conftest.py"})
