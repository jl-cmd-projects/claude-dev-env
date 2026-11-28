"""Check, from inside a started thread, that it has its repos and the owner's setup.

The thread runs this file twice. The first run, ``locate``, names the repos
that are not cloned yet, so the thread can attach them::

    python3 thread_start_probe.py locate --repos Echo-Visuals-Inc/agent-channels,JonEcho/theme-planning

The second run, ``finish``, runs Test 1 and Test 2 and prints one line that
starts with ``THREAD_PROBE_RESULT``, followed by the JSON the grader reads::

    python3 thread_start_probe.py finish --repos <same list> --branch claude/thread-probe-<case>

Test 1 (repo access): each repo is cloned, a fetch works, a push of the test
branch works, and the test branch is deleted after.

Test 2 (setup ran): the setup logs show each step ran and did its work, no
``Setup skipped`` notice exists, doctor.sh prints no FAIL, no
``WARN project-settings`` and no ``WARN start-refresh``, the named skills
loaded, and the transcript gate refused the probe search.

The file uses only the standard library, because a thread whose setup did not
run has no other packages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

CLAUDE_HOME = Path.home() / ".claude"
SETUP_LOG = CLAUDE_HOME / "setup.log"
SETUP_BACKGROUND_LOG = CLAUDE_HOME / "setup-background.log"
SETUP_SKIPPED_MARKER = CLAUDE_HOME / "setup-skipped-pending"
SETUP_NOTICE = CLAUDE_HOME / "setup-notice.json"
TRANSCRIPT_ROOT = CLAUDE_HOME / "projects"
ALL_CHECKOUT_PARENTS = (
    Path("/home/user"),
    Path("/workspace"),
    Path.home(),
    Path("/tmp"),
)
ALL_FOREGROUND_STEPS = (
    "apply_auto_mode_rules",
    "apply_permission_rules",
    "apply_auto_compact_windows",
    "apply_merge_review_settings",
    "apply_repository_opt_in_settings",
    "register_threaded_agent_gate",
    "install_pillow_for_path_python",
    "link_python_automation_skills",
    "export_ntfy_settings",
    "configure_grok_sign_in",
    "pin_prompt_cache",
    "register_mailbox_join",
    "register_session_archive",
    "register_refresh_on_start",
    "expose_claude_project_skills",
)
ALL_BACKGROUND_STEPS = (
    "update_claude_dev_env",
    "install_account_plugins",
    "relink_plugin_skills",
    "link_python_automation_skills",
    "install_powershell",
    "install_bws",
    "install_grok_cli",
    "build_python_automation_check_environment",
    "link_playwright_browsers",
    "provision_theme_db_postgres",
)
SKIPPED_WORK_PATTERN = re.compile(
    r"no python-automation checkout|no python-automation Git checkout|"
    r"not linked|checkout not found|Setup skipped|Setup incomplete|"
    r"plugins not installed|Action needed \(",
)
ALL_FORBIDDEN_DOCTOR_LINES = (
    re.compile(r"^FAIL\s"),
    re.compile(r"^WARN\s+project-settings\s"),
    re.compile(r"^WARN\s+start-refresh\s"),
)
ALL_REQUIRED_SKILLS = ("pr-lifecycle", "verify-cloud-session-start")
GATE_PROBE_NEEDLE = "thread-probe-needle"
GATE_REFUSAL_TEXT = "BLOCKED"
RESULT_PREFIX = "THREAD_PROBE_RESULT "
COMMAND_TIMEOUT_SECONDS = 180


def run_command(
    all_arguments: list[str], working_directory: Path | None = None
) -> dict:
    try:
        completed = subprocess.run(
            all_arguments,
            cwd=working_directory,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"ok": False, "exit": None, "tail": str(error)[-400:]}
    output_text = (completed.stdout + completed.stderr).strip()
    return {
        "ok": completed.returncode == 0,
        "exit": completed.returncode,
        "tail": output_text[-400:],
    }


def origin_slug(checkout: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(checkout), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    match = re.search(
        r"github\.com[/:]([^/]+)/([^/.]+?)(?:\.git)?/?$", result.stdout.strip()
    )
    return f"{match.group(1)}/{match.group(2)}".lower() if match else ""


def find_checkout(repository_slug: str) -> Path | None:
    wanted_slug = repository_slug.lower()
    for each_parent in ALL_CHECKOUT_PARENTS:
        if not each_parent.is_dir():
            continue
        try:
            all_children = sorted(each_parent.iterdir())
        except OSError:
            continue
        for each_child in [each_parent, *all_children]:
            if (each_child / ".git").exists() and origin_slug(
                each_child
            ) == wanted_slug:
                return each_child
    return None


def check_repository(repository_slug: str, test_branch: str) -> dict:
    checkout = find_checkout(repository_slug)
    if checkout is None:
        return {
            "repo": repository_slug,
            "cloned": False,
            "fetch": None,
            "push": None,
            "delete": None,
            "ok": False,
        }
    fetch_result = run_command(
        ["git", "fetch", "-q", "--depth=1", "origin", "HEAD"], checkout
    )
    push_result = run_command(
        ["git", "push", "-q", "origin", f"HEAD:refs/heads/{test_branch}"], checkout
    )
    delete_result = (
        run_command(["git", "push", "-q", "origin", "--delete", test_branch], checkout)
        if push_result["ok"]
        else {"ok": False, "exit": None, "tail": "push failed, nothing to delete"}
    )
    is_ok = fetch_result["ok"] and push_result["ok"] and delete_result["ok"]
    return {
        "repo": repository_slug,
        "cloned": True,
        "path": str(checkout),
        "fetch": fetch_result,
        "push": push_result,
        "delete": delete_result,
        "ok": is_ok,
    }


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def step_outcomes(log_text: str) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    for each_match in re.finditer(
        r"^== step: (\S+)(?: (ok|failed.*))?$", log_text, re.MULTILINE
    ):
        step_name, outcome = each_match.group(1), each_match.group(2)
        if outcome:
            outcomes[step_name] = "ok" if outcome == "ok" else outcome
        else:
            outcomes.setdefault(step_name, "started")
    return outcomes


def check_setup() -> dict:
    setup_text = read_text(SETUP_LOG)
    background_text = read_text(SETUP_BACKGROUND_LOG)
    foreground_outcomes = step_outcomes(setup_text)
    background_outcomes = step_outcomes(background_text)
    all_problems: list[str] = []
    for each_step in ALL_FOREGROUND_STEPS:
        if foreground_outcomes.get(each_step) != "ok":
            all_problems.append(
                f"setup.log step {each_step}: {foreground_outcomes.get(each_step, 'missing')}"
            )
    for each_step in ALL_BACKGROUND_STEPS:
        if background_outcomes.get(each_step) != "ok":
            all_problems.append(
                f"setup-background.log step {each_step}: {background_outcomes.get(each_step, 'missing')}"
            )
    if "== background finished" not in background_text:
        all_problems.append("setup-background.log has no '== background finished' line")
    all_skip_lines = [
        each_line.strip()[:200]
        for each_line in (setup_text + "\n" + background_text).splitlines()
        if SKIPPED_WORK_PATTERN.search(each_line)
    ]
    all_problems.extend(
        f"setup log line: {each_line}" for each_line in all_skip_lines[:8]
    )
    notice_text = read_text(SETUP_NOTICE)
    has_skip_notice = SETUP_SKIPPED_MARKER.exists() or "Setup skipped" in setup_text
    if has_skip_notice:
        all_problems.append("a Setup skipped notice exists")
    if notice_text:
        all_problems.append("setup-notice.json exists: " + notice_text[:200])
    return {
        "setup_log_present": SETUP_LOG.is_file(),
        "foreground_steps": foreground_outcomes,
        "background_steps": background_outcomes,
        "setup_skipped_notice": has_skip_notice,
        "problems": all_problems,
        "ok": not all_problems,
    }


def check_doctor() -> dict:
    checkout = find_checkout("Echo-Visuals-Inc/python-automation")
    if checkout is None:
        return {
            "ran": False,
            "lines": [],
            "forbidden": ["no python-automation checkout, so doctor.sh cannot run"],
            "ok": False,
        }
    doctor_path = (
        checkout
        / ".claude"
        / "skills"
        / "verify-cloud-session-start"
        / "scripts"
        / "doctor.sh"
    )
    result = subprocess.run(
        ["bash", str(doctor_path), str(checkout)],
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
        check=False,
    )
    all_lines = [
        each_line for each_line in result.stdout.splitlines() if each_line.strip()
    ]
    all_forbidden = [
        each_line
        for each_line in all_lines
        if any(
            each_pattern.search(each_line)
            for each_pattern in ALL_FORBIDDEN_DOCTOR_LINES
        )
    ]
    return {
        "ran": True,
        "lines": all_lines,
        "forbidden": all_forbidden,
        "ok": not all_forbidden,
    }


def newest_transcript() -> Path | None:
    session_identifier = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    all_candidates: list[Path] = []
    if TRANSCRIPT_ROOT.is_dir():
        for each_project in TRANSCRIPT_ROOT.iterdir():
            if each_project.is_dir():
                all_candidates.extend(each_project.glob("*.jsonl"))
    for each_candidate in all_candidates:
        if session_identifier and each_candidate.stem == session_identifier:
            return each_candidate
    return max(all_candidates, key=lambda each: each.stat().st_mtime, default=None)


def tool_result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(each.get("text", "")) for each in content if isinstance(each, dict)
        )
    return ""


def check_transcript() -> dict:
    transcript = newest_transcript()
    if transcript is None:
        return {"transcript": None, "skills": {}, "gate_refused": False, "ok": False}
    all_tool_uses: dict[str, dict] = {}
    all_results: dict[str, tuple[bool, str]] = {}
    for each_line in read_text(transcript).splitlines():
        try:
            record = json.loads(each_line)
        except ValueError:
            continue
        message = record.get("message") if isinstance(record, dict) else None
        if not isinstance(message, dict) or not isinstance(
            message.get("content"), list
        ):
            continue
        for each_block in message["content"]:
            if not isinstance(each_block, dict):
                continue
            if each_block.get("type") == "tool_use":
                all_tool_uses[each_block.get("id", "")] = each_block
            elif each_block.get("type") == "tool_result":
                all_results[each_block.get("tool_use_id", "")] = (
                    bool(each_block.get("is_error")),
                    tool_result_text(each_block.get("content")),
                )
    skill_outcomes = {each_skill: "not called" for each_skill in ALL_REQUIRED_SKILLS}
    gate_refused = False
    gate_detail = "probe search not run"
    for each_identifier, each_use in all_tool_uses.items():
        tool_input = (
            each_use.get("input") if isinstance(each_use.get("input"), dict) else {}
        )
        is_error, result_text = all_results.get(each_identifier, (True, "no result"))
        if each_use.get("name") == "Skill":
            skill_name = str(tool_input.get("skill", "")).split(":")[-1]
            if skill_name in skill_outcomes and skill_outcomes[skill_name] != "loaded":
                skill_outcomes[skill_name] = (
                    "failed: " + result_text[:160] if is_error else "loaded"
                )
        if each_use.get("name") == "Bash" and GATE_PROBE_NEEDLE in str(
            tool_input.get("command", "")
        ):
            gate_refused = gate_refused or (
                is_error and GATE_REFUSAL_TEXT in result_text
            )
            gate_detail = result_text[:200]
    is_ok = gate_refused and all(each == "loaded" for each in skill_outcomes.values())
    return {
        "transcript": str(transcript),
        "skills": skill_outcomes,
        "gate_refused": gate_refused,
        "gate_detail": gate_detail,
        "ok": is_ok,
    }


def own_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def split_repositories(text: str) -> list[str]:
    return [each.strip() for each in text.split(",") if each.strip()]


def locate(all_repositories: list[str]) -> None:
    all_missing = [each for each in all_repositories if find_checkout(each) is None]
    print("MISSING " + (",".join(all_missing) if all_missing else "none"))


def finish(all_repositories: list[str], test_branch: str) -> None:
    all_repository_checks = [
        check_repository(each, test_branch) for each in all_repositories
    ]
    setup_check = check_setup()
    doctor_check = check_doctor()
    transcript_check = check_transcript()
    test_one_ok = bool(all_repository_checks) and all(
        each["ok"] for each in all_repository_checks
    )
    test_two_ok = setup_check["ok"] and doctor_check["ok"] and transcript_check["ok"]
    result = {
        "probe_sha256": own_sha256(),
        "session": os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID", ""),
        "cwd_at_start": os.environ.get("PWD", ""),
        "test_1": {"ok": test_one_ok, "repos": all_repository_checks},
        "test_2": {
            "ok": test_two_ok,
            "setup": setup_check,
            "doctor": doctor_check,
            "transcript": transcript_check,
        },
    }
    Path("/tmp/thread_probe_result.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(RESULT_PREFIX + json.dumps(result, separators=(",", ":")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("locate", "finish"))
    parser.add_argument("--repos", required=True)
    parser.add_argument("--branch", default="claude/thread-probe")
    arguments = parser.parse_args()
    all_repositories = split_repositories(arguments.repos)
    if arguments.action == "locate":
        locate(all_repositories)
    else:
        finish(all_repositories, arguments.branch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
