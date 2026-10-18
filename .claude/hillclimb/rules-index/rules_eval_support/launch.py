"""Start a headless Claude Code session, through the account broker or on the caller's account."""

import shutil
from pathlib import Path

from session_eval_support import session
from session_eval_support.session import SessionRun, SessionSettings, brokered_words


def launch_words(report_path: Path, all_claude_words: list[str], is_direct: bool) -> list[str]:
    """Return the command that starts one headless Claude call.

    ::

        launch_words(r, ["claude", "-p", "hi"], is_direct=True)
        -> ["claude", "-p", "hi"]
        launch_words(r, ["claude", "-p", "hi"], is_direct=False)
        -> [python, account_broker.py, "run", "--product", "claude", "--report", r, "--", "claude", "-p", "hi"]

    Args:
        report_path: Where the broker writes its report.
        all_claude_words: The claude command and its arguments.
        is_direct: Whether to run on the account the caller's session uses.

    Returns:
        The full argument list for subprocess.
    """
    if is_direct:
        return [shutil.which(all_claude_words[0]) or all_claude_words[0], *all_claude_words[1:]]
    return brokered_words(report_path, all_claude_words)


def run_session(workspace: Path, prompt: str, settings: SessionSettings, is_direct: bool) -> SessionRun:
    """Run the prompt as one headless session in the workspace and read its stream.

    Args:
        workspace: The prepared workspace, used as the session's directory.
        prompt: The case's ask.
        settings: The model, effort, turn cap and wall-clock ceiling.
        is_direct: Whether to skip the broker and run on the caller's account.

    Returns:
        The stream, latency, exit code (None on timeout) and broker report.
    """
    return session.run_session(
        workspace,
        prompt,
        settings,
        lambda report_path, all_claude_words: launch_words(report_path, all_claude_words, is_direct),
    )
