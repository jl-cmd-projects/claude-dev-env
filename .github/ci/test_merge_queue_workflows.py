"""Specifications for the merge_group wiring of the required-check workflows.

A merge queue on main waits for every required status check on the merge
group commit. Each workflow that reports one of those checks must trigger on
merge_group, and each job that reads pull request fields must skip there or read the
queue branch name.
"""

import os
import subprocess
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


def test_package_suite_covers_usage_wrapup_with_required_runtimes() -> None:
    workflow = load_workflow("ci-tests.yml")
    all_steps = workflow["jobs"]["python"]["steps"]
    suite_index = next(
        index for index, step in enumerate(all_steps)
        if "python -m pytest" in step.get("run", "")
    )
    assert "packages/usage-wrapup/tests" in all_steps[suite_index]["run"]
    setup_steps = all_steps[:suite_index]
    assert any(step.get("uses", "").startswith("oven-sh/setup-bun@") for step in setup_steps)
    assert any("@anthropic-ai/claude-code@" in step.get("run", "") for step in setup_steps)
    filter_step = next(
        step for step in workflow["jobs"]["changes"]["steps"] if step.get("id") == "filter"
    )
    filters = yaml.safe_load(filter_step["with"]["filters"])
    assert "packages/usage-wrapup/**" in filters["package_suite"]
