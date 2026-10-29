"""Specifications for the merge_group wiring of the required-check workflows.

A merge queue on main waits for every required status check on the merge
group commit. Each workflow that reports one of those checks must trigger on
merge_group, and each job that reads pull request fields must skip there or read the
queue branch name.
"""

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

WORKFLOWS_DIRECTORY = Path(__file__).resolve().parents[1] / "workflows"
MERGE_GROUP_EVENT = "merge_group"
ALL_REQUIRED_CHECK_WORKFLOW_NAMES = (
    "ci-tests.yml",
    "pr-check.yml",
    "private-terms.yml",
    "review-closure.yml",
    "validate-instruction-pairs.yml",
)
ALL_PULL_REQUEST_ONLY_JOBS = (
    ("pr-check.yml", "validate"),
    ("pr-check.yml", "fix-test-proof"),
    ("private-terms.yml", "scan"),
)


def load_workflow(workflow_name: str) -> dict:
    return yaml.safe_load(
        (WORKFLOWS_DIRECTORY / workflow_name).read_text(encoding="utf-8")
    )


def read_triggers(workflow: dict) -> dict:
    return workflow.get("on", workflow.get(True))


@pytest.mark.parametrize("workflow_name", ALL_REQUIRED_CHECK_WORKFLOW_NAMES)
def test_required_check_workflow_triggers_on_merge_group(workflow_name: str) -> None:
    assert MERGE_GROUP_EVENT in read_triggers(load_workflow(workflow_name))


@pytest.mark.parametrize(("workflow_name", "job_key"), ALL_PULL_REQUEST_ONLY_JOBS)
def test_pull_request_only_job_skips_on_merge_group(
    workflow_name: str, job_key: str
) -> None:
    job_condition = load_workflow(workflow_name)["jobs"][job_key]["if"]

    assert (
        "github.event_name == 'pull_request'" in job_condition
        or "github.event_name != 'merge_group'" in job_condition
    )


@pytest.mark.parametrize(
    ("workflow_name", "concurrency_group"),
    (
        (
            "private-terms.yml",
            load_workflow("private-terms.yml")["concurrency"]["group"],
        ),
        (
            "review-closure.yml",
            load_workflow("review-closure.yml")["jobs"]["review-closure"][
                "concurrency"
            ]["group"],
        ),
    ),
)
def test_concurrency_group_keys_each_merge_group_apart(
    workflow_name: str, concurrency_group: str
) -> None:
    assert "github.event.merge_group.head_sha" in concurrency_group, workflow_name


def test_review_closure_reads_the_pull_request_number_from_the_queue_branch(
    tmp_path: Path,
) -> None:
    review_closure_steps = load_workflow("review-closure.yml")["jobs"][
        "review-closure"
    ]["steps"]
    closure_script = review_closure_steps[-1]["run"]
    recording_python = tmp_path / "python"
    recording_python.write_text('#!/bin/sh\necho "$2 $3"\n', encoding="utf-8")
    recording_python.chmod(0o755)
    queue_environment = {
        **load_workflow("review-closure.yml")["env"],
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "GITHUB_EVENT_NAME": MERGE_GROUP_EVENT,
        "REPOSITORY": "owner/name",
        "PULL_REQUEST_NUMBER": "",
        "MERGE_GROUP_HEAD_REF": "refs/heads/gh-readonly-queue/main/pr-1442-0123456789abcdef",
    }

    completed_closure = subprocess.run(
        ["bash", "-c", closure_script],
        env=queue_environment,
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed_closure.stdout.strip() == "owner/name 1442"


def test_committed_tree_compares_a_merge_group_against_its_base() -> None:
    committed_tree_steps = load_workflow("ci-tests.yml")["jobs"]["committed-tree"][
        "steps"
    ]
    merge_base_step = next(
        each_step
        for each_step in committed_tree_steps
        if each_step.get("id") == "event-merge-base"
    )

    assert (
        "github.event.merge_group.base_sha"
        in merge_base_step["env"]["EVENT_BASE_REVISION"]
    )


def test_path_filter_step_skips_on_merge_group() -> None:
    change_steps = load_workflow("ci-tests.yml")["jobs"]["changes"]["steps"]
    filter_step = next(
        each_step for each_step in change_steps if each_step.get("id") == "filter"
    )

    assert filter_step["if"] == "github.event_name != 'merge_group'"


@pytest.mark.parametrize(
    ("head_status_json", "expected_queue_state"),
    [
        ('{"statuses": [{"context": "Merge review", "state": "success"}]}', "success"),
        ('{"statuses": [{"context": "Merge review", "state": "failure"}]}', "failure"),
        ('{"statuses": []}', "failure"),
    ],
)
def test_merge_review_status_carries_the_head_verdict_to_the_queue_commit(
    tmp_path: Path, head_status_json: str, expected_queue_state: str
) -> None:
    carry_step = load_workflow("merge-review-status.yml")["jobs"]["carry"]["steps"][0]
    posted_path = tmp_path / "posted"
    fake_gh = tmp_path / "gh"
    fake_gh.write_text(
        "#!/bin/sh\n"
        'case "$2" in\n'
        '  */pulls/1442) echo headsha ;;\n'
        f"  */commits/headsha/status) echo '{head_status_json}' ;;\n"
        f'  */statuses/queuesha) echo "$2 $4 $6" > {posted_path} ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    queue_environment = {
        **carry_step["env"],
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "GH_REPO": "owner/name",
        "MERGE_GROUP_HEAD_REF": "refs/heads/gh-readonly-queue/main/pr-1442-0123456789abcdef",
        "MERGE_GROUP_HEAD_SHA": "queuesha",
    }

    subprocess.run(
        ["bash", "-c", carry_step["run"]],
        env=queue_environment,
        capture_output=True,
        text=True,
        check=True,
    )

    assert posted_path.read_text(encoding="utf-8").split() == [
        "repos/owner/name/statuses/queuesha",
        f"state={expected_queue_state}",
        "context=Merge",
        "review",
    ]


REVIEW_RECORD_BODY = (
    '<!-- codex-pr-review:v1 {"finding_count": 0, "head_sha": "abc123"} -->\n'
    "Codex review finished on `abc123`: 0 findings."
)


@pytest.mark.parametrize("job_key", ("review-closure", "review-closure-comment"))
def test_review_closure_counts_a_bot_review_record_as_a_notice(
    tmp_path: Path, job_key: str
) -> None:
    workflow = load_workflow("review-closure.yml")
    closure_script = workflow["jobs"][job_key]["steps"][-1]["run"]
    recorded_arguments = tmp_path / "arguments"
    recording_python = tmp_path / "python"
    recording_python.write_text(
        f'#!/bin/sh\nshift\nprintf "%s\\n" "$@" > "{recorded_arguments}"\n',
        encoding="utf-8",
    )
    recording_python.chmod(0o755)
    stub_gh = tmp_path / "gh"
    stub_gh.write_text("#!/bin/sh\necho 0123456789abcdef\n", encoding="utf-8")
    stub_gh.chmod(0o755)
    step_environment = {
        **workflow["env"],
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "GITHUB_EVENT_NAME": "pull_request",
        "REPOSITORY": "owner/name",
        "PULL_REQUEST_NUMBER": "7",
        "MERGE_GROUP_HEAD_REF": "",
    }
    subprocess.run(["bash", "-c", closure_script], env=step_environment, check=True)
    scripts_directory = (
        Path(__file__).resolve().parents[2] / "packages/claude-dev-env/scripts"
    )
    sys.path.insert(0, str(scripts_directory))
    try:
        review_closure = importlib.import_module("review_closure")
        review_closure_model = importlib.import_module("review_closure_model")
    finally:
        sys.path.remove(str(scripts_directory))
    parsed = review_closure.build_parser().parse_args(
        recorded_arguments.read_text(encoding="utf-8").splitlines()
    )

    record = review_closure_model.parse_top_level_comment(
        {
            "id": 1,
            "body": REVIEW_RECORD_BODY,
            "user": {"login": "review-app[bot]", "type": "Bot"},
            "created_at": "2026-10-23T00:00:00+00:00",
            "updated_at": "2026-10-23T00:00:00+00:00",
        },
        parsed.notice_marker,
    )

    assert record.is_notice
