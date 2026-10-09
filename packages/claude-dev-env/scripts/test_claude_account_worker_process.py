from __future__ import annotations

from pathlib import Path

from claude_account_worker_process import invoke_worker
from dev_env_scripts_constants.account_broker_constants import JobOutcome, Product


def test_should_send_job_to_runner_and_return_outcome_with_elapsed_seconds(
    tmp_path: Path,
) -> None:
    expected_outcome = JobOutcome(
        0, "{}", "", "extra_2", (("extra_2", "served"),), "served", None, None
    )
    captured_calls: list[tuple[Product, list[str], dict[str, object]]] = []
    clock_readings = iter([100.0, 107.5])

    def recording_runner(
        product: Product, argv: list[str], **options: object
    ) -> JobOutcome:
        captured_calls.append((product, argv, options))
        return expected_outcome

    outcome, elapsed_seconds = invoke_worker(
        all_arguments=["claude", "-p"],
        cwd=tmp_path,
        prompt_text="standalone brief",
        timeout_minutes=2,
        runner=recording_runner,
        monotonic_clock=lambda: next(clock_readings),
    )

    assert outcome is expected_outcome
    assert elapsed_seconds == 7.5
    assert captured_calls == [
        (
            Product.CLAUDE,
            ["claude", "-p"],
            {
                "timeout_seconds": 120,
                "stdin_text": "standalone brief",
                "cwd": tmp_path,
                "encoding": "utf-8",
                "errors": "replace",
            },
        )
    ]


def test_should_pass_the_live_log_to_the_runner_when_one_is_named(tmp_path: Path) -> None:
    live_log = tmp_path / "events.jsonl"
    captured_options: dict[str, object] = {}

    def recording_runner(product: Product, argv: list[str], **options: object) -> JobOutcome:
        captured_options.update(options)
        return JobOutcome(0, "{}", "", "main", (), "served", None, None)

    invoke_worker(
        all_arguments=["claude", "-p"],
        cwd=tmp_path,
        prompt_text="brief",
        timeout_minutes=1,
        runner=recording_runner,
        live_log=live_log,
    )

    assert captured_options["live_log"] == live_log
