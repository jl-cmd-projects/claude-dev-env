"""Behavioral tests for the executable Codex Astra advisor path."""
import importlib.util
import io
import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parents[2] / "scripts"))

from account_broker import choose_from_readings, decision_payload, readings_payload
from dev_env_scripts_constants.account_broker_constants import Account, Meters, Product, Reading

_ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]


def _load_astra_module() -> ModuleType:
    scripts_root = Path(__file__).parent.parent
    config_root = str(scripts_root / "config")
    if config_root not in sys.path:
        sys.path.insert(0, config_root)
    specification = importlib.util.spec_from_file_location(
        "codex_astra_advisor", scripts_root / "codex_astra_advisor.py"
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


astra_advisor = _load_astra_module()

SCRIPTS_ROOT = Path(__file__).parent.parent
BROKER_PATH = SCRIPTS_ROOT.parents[2] / "scripts" / "account_broker.py"
PICKED_CODEX_HOME = Path("codex-profiles") / "codex-2"
NORMAL_ANSWER = {
    "decision": {
        "action": "run",
        "tier": "normal",
        "account": "codex-2",
        "home": str(PICKED_CODEX_HOME),
        "resets_at": None,
        "reason": "codex-2 has 90% left",
    },
    "accounts": [{
        "name": "codex-2",
        "home": str(PICKED_CODEX_HOME),
        "is_main": False,
        "meters": {
            "session_percent_left": 90,
            "session_resets_at": None,
            "weekly_percent_left": 95,
            "weekly_resets_at": None,
        },
    }],
}
ENABLED_SETTINGS = {astra_advisor.ASTRA_ENV_VAR: "1"}


@pytest.fixture(autouse=True)
def _codex_on_search_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(astra_advisor.shutil, "which", lambda name: "codex")


def _broker_answer(payload: object, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        [sys.executable, str(BROKER_PATH), "choose", "--product", "codex"],
        returncode,
        json.dumps(payload),
        "",
    )


def _events(session_id: str = "thread-1", guidance: str = "PLAN\ninspect") -> str:
    return "\n".join(
        (
            json.dumps({"type": "thread.started", "thread_id": session_id}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": guidance},
                }
            ),
        )
    )


def _two_step_runner(
    all_calls: list[list[str]],
    guidance: str = "PLAN\ninspect",
    all_call_keywords: list[dict[str, object]] | None = None,
) -> _ProcessRunner:
    def runner(
        arguments: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        all_calls.append(arguments)
        if all_call_keywords is not None:
            all_call_keywords.append(kwargs)
        if len(all_calls) == 1:
            return _broker_answer(NORMAL_ANSWER)
        return subprocess.CompletedProcess(arguments, 0, _events(guidance=guidance), "")
    return runner


@pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "yes", "on", " On "])
def test_astra_flag_accepts_documented_truthy_values(truthy: str) -> None:
    assert astra_advisor.is_astra_advisor_enabled({"ADVISOR_ASTRA": truthy})


def test_astra_flag_rejects_legacy_sol_setting() -> None:
    assert not astra_advisor.is_astra_advisor_enabled({"ADVISOR_SOL": "1"})


def test_resolve_advisor_effort_uses_shared_setting_and_default() -> None:
    assert astra_advisor.resolve_advisor_effort({"ADVISOR_EFFORT": "HIGH"}) == "high"
    with pytest.raises(RuntimeError, match="effort is unknown"):
        astra_advisor.resolve_advisor_effort({"ADVISOR_EFFORT": "unknown"})
    assert astra_advisor.resolve_advisor_effort({"ADVISOR_EFFORT": "Light"}) == "low"
    assert astra_advisor.resolve_advisor_effort({"ADVISOR_EFFORT": "XHIGH"}) == "medium"
    assert astra_advisor.resolve_advisor_effort({"ADVISOR_EFFORT": "MAX"}) == "medium"


def test_advisor_route_uses_edited_policy_model_and_effort(tmp_path: Path) -> None:
    policy = json.loads(
        (SCRIPTS_ROOT.parents[2] / "rules" / "subagent-model-policy.json").read_text(
            encoding="utf-8"
        )
    )
    for each_entry in policy["roleReplacements"]:
        if (
            each_entry["role"] == "advisor"
            and each_entry["requested"] == {"model": "astra", "effort": "xhigh"}
        ):
            each_entry["selected"] = {"model": "luna", "effort": "high"}
    policy_path = tmp_path / "subagent-model-policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    assert astra_advisor.resolve_advisor_pair(
        {"ADVISOR_EFFORT": "xhigh"}, policy_path
    ) == ("gpt-5.6-luna", "high")


def test_advisor_route_blocks_malformed_policy(tmp_path: Path) -> None:
    policy_path = tmp_path / "subagent-model-policy.json"
    policy_path.write_text('{"schemaVersion": 1}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="models must be an object"):
        astra_advisor.resolve_advisor_pair({}, policy_path)


def test_resolve_codex_executable_prefers_override_and_falls_back_to_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert astra_advisor.resolve_codex_executable(
        {astra_advisor.ADVISOR_CODEX_EXECUTABLE_ENV_VAR: "/tmp/codex-custom"}
    ) == "/tmp/codex-custom"
    monkeypatch.setattr(astra_advisor.shutil, "which", lambda name: "/usr/bin/codex")
    assert astra_advisor.resolve_codex_executable({}) == "/usr/bin/codex"


@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh", "max"])
def test_codex_arguments_apply_selected_effort(effort: str) -> None:
    arguments = astra_advisor.build_codex_arguments("codex", reasoning_effort=effort)
    config_index = arguments.index("--config")
    assert arguments[config_index + 1] == f'model_reasoning_effort="{effort}"'


def test_codex_arguments_use_astra_and_read_only_sandbox() -> None:
    arguments = astra_advisor.build_codex_arguments("codex", session_id="thread-1")
    assert arguments[:4] == ["codex", "exec", "--model", "gpt-6-astra"]
    assert ["--sandbox", "read-only"] == arguments[6:8]
    assert arguments[-3:] == ["resume", "thread-1", "-"]


def test_argument_parser_accepts_astra_and_rejects_sol() -> None:
    parser = astra_advisor.build_argument_parser()
    parsed = parser.parse_args(["--bind", "--cwd", ".", "--enable-astra"])
    assert parsed.is_astra_requested
    assert parser.parse_args(["--bind", "--cwd", ".", "--effort", "light"]).astra_effort == "light"
    with pytest.raises(SystemExit):
        parser.parse_args(["--bind", "--cwd", ".", "--enable-sol"])


def test_should_resolve_packaged_account_broker_path() -> None:
    path = astra_advisor.resolve_account_broker_path()
    assert path == BROKER_PATH.resolve()
    assert path.is_file()


def test_should_run_broker_choose_command_for_codex_preflight() -> None:
    all_calls: list[list[str]] = []

    def runner(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        all_calls.append(arguments)
        return _broker_answer(NORMAL_ANSWER)

    astra_advisor.run_astra_preflight(BROKER_PATH, runner)
    assert all_calls == [
        [sys.executable, str(BROKER_PATH), "choose", "--product", "codex", "--require-tier", "normal"]
    ]


def test_should_accept_normal_tier_and_keep_its_codex_home() -> None:
    preflight = astra_advisor.run_astra_preflight(
        BROKER_PATH, lambda arguments, **kwargs: _broker_answer(NORMAL_ANSWER)
    )
    assert preflight.eligible
    assert preflight.percent_left == 90
    assert preflight.codex_home == PICKED_CODEX_HOME


@pytest.mark.parametrize("tier", ["luna", "wait"])
def test_should_decline_a_tier_without_room(tier: str) -> None:
    answer = {
        **NORMAL_ANSWER,
        "decision": {**NORMAL_ANSWER["decision"], "tier": tier, "reason": "every account is low"},
    }
    preflight = astra_advisor.run_astra_preflight(
        BROKER_PATH, lambda arguments, **kwargs: _broker_answer(answer)
    )
    assert not preflight.eligible
    assert preflight.fallback_kind == astra_advisor.ASTRA_FALLBACK_KIND_DECLINED
    assert preflight.codex_home is None


@pytest.mark.parametrize(
    "payload",
    [
        {"decision": {"tier": None}},
        {**NORMAL_ANSWER, "decision": {**NORMAL_ANSWER["decision"], "home": None}},
        {
            **NORMAL_ANSWER,
            "accounts": [{
                "name": "codex-2",
                "home": str(PICKED_CODEX_HOME),
                "meters": {"session_percent_left": "90"},
            }],
        },
        {
            **NORMAL_ANSWER,
            "accounts": [{
                **NORMAL_ANSWER["accounts"][0],
                "home": "codex-profiles/codex-1",
            }],
        },
        ["bad"],
    ],
)
def test_should_reject_a_malformed_broker_answer(payload: object) -> None:
    preflight = astra_advisor.run_astra_preflight(
        BROKER_PATH, lambda arguments, **kwargs: _broker_answer(payload)
    )
    assert not preflight.eligible
    assert preflight.fallback_kind == astra_advisor.ASTRA_FALLBACK_KIND_BROKEN


def test_should_reject_failed_broker_preflight() -> None:
    preflight = astra_advisor.run_astra_preflight(
        BROKER_PATH, lambda arguments, **kwargs: _broker_answer(NORMAL_ANSWER, returncode=1)
    )
    assert not preflight.eligible
    assert preflight.fallback_kind == astra_advisor.ASTRA_FALLBACK_KIND_BROKEN


@pytest.mark.parametrize("signal", ["ENDORSE", "CORRECTION", "PLAN", "STOP"])
def test_jsonl_parser_accepts_guidance_signals(signal: str) -> None:
    reply = astra_advisor.parse_codex_jsonl_reply(
        _events(guidance=f"{signal}\nmore"), None, True
    )
    assert reply.successful
    assert reply.signal == signal


@pytest.mark.parametrize(
    "jsonl_text",
    [
        "{broken",
        json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
        _events(guidance="PLAN: inspect"),
    ],
)
def test_jsonl_parser_falls_back_for_invalid_reply(jsonl_text: str) -> None:
    reply = astra_advisor.parse_codex_jsonl_reply(jsonl_text, None, True)
    assert reply.is_fallback
    assert not reply.successful


def test_should_bind_under_the_broker_chosen_home() -> None:
    calls: list[list[str]] = []
    all_call_keywords: list[dict[str, object]] = []
    reply = astra_advisor.run_codex_astra_advisor(
        "consult",
        Path("."),
        None,
        BROKER_PATH,
        ENABLED_SETTINGS,
        None,
        _two_step_runner(calls, all_call_keywords=all_call_keywords),
    )
    codex_environment = all_call_keywords[1]["env"]
    assert isinstance(codex_environment, dict)
    assert codex_environment["CODEX_HOME"] == str(PICKED_CODEX_HOME)
    assert reply.successful
    assert reply.selected_tier == "Astra"
    assert reply.outcome == "codex"
    assert reply.session_id == "thread-1"
    assert reply.guidance == "PLAN\ninspect"
    assert reply.signal == "PLAN"
    assert reply.fallback_kind is None
    assert calls[1] == astra_advisor.build_codex_arguments("codex")


def test_injected_preflight_without_a_codex_home_fails_closed() -> None:
    all_started_commands: list[list[str]] = []

    def runner_that_must_not_start(
        all_arguments: list[str], **_keywords: object
    ) -> subprocess.CompletedProcess[str]:
        all_started_commands.append(all_arguments)
        raise AssertionError("no process may start without a chosen Codex home")

    reply = astra_advisor.run_codex_astra_advisor(
        "consult",
        Path("."),
        astra_advisor.AstraPreflight(True, 90, "ok"),
        BROKER_PATH,
        ENABLED_SETTINGS,
        None,
        runner_that_must_not_start,
    )

    assert reply.is_fallback
    assert reply.fallback_kind == astra_advisor.ASTRA_FALLBACK_KIND_BROKEN
    assert astra_advisor.ASTRA_NO_HOME_REASON in (reply.reason or "")
    assert all_started_commands == []


def test_bind_routes_astra_xhigh_to_the_policy_effort() -> None:
    calls: list[list[str]] = []
    settings = {**ENABLED_SETTINGS, astra_advisor.ADVISOR_EFFORT_ENV_VAR: "xhigh"}
    reply = astra_advisor.run_codex_astra_advisor(
        "consult",
        Path("."),
        None,
        BROKER_PATH,
        settings,
        None,
        _two_step_runner(calls),
    )
    assert reply.successful
    config_index = calls[1].index("--config")
    assert calls[1][config_index + 1] == 'model_reasoning_effort="medium"'


def test_disabled_flag_returns_declined_fallback() -> None:
    reply = astra_advisor.run_codex_astra_advisor(
        "consult",
        Path("."),
        astra_advisor.AstraPreflight(True, 90, "ok"),
        None,
        {},
        None,
        subprocess.run,
    )
    assert reply.is_fallback
    assert reply.fallback_kind == astra_advisor.ASTRA_FALLBACK_KIND_DECLINED


def test_missing_codex_returns_broken_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(astra_advisor.shutil, "which", lambda name: None)
    reply = astra_advisor.run_codex_astra_advisor(
        "consult", Path("."), None, BROKER_PATH, ENABLED_SETTINGS, None, subprocess.run
    )
    assert reply.is_fallback
    assert reply.fallback_kind == astra_advisor.ASTRA_FALLBACK_KIND_BROKEN


def test_resume_uses_existing_session() -> None:
    calls: list[list[str]] = []
    reply = astra_advisor.run_codex_astra_advisor(
        "resume",
        Path("."),
        None,
        BROKER_PATH,
        ENABLED_SETTINGS,
        "thread-1",
        _two_step_runner(calls, "ENDORSE\nready"),
    )
    assert reply.successful
    assert calls[1][-3:] == ["resume", "thread-1", "-"]


def test_main_serializes_result_and_astra_fields(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        astra_advisor,
        "run_codex_astra_advisor",
        lambda *args, **kwargs: astra_advisor.CodexAstraAdvisorReply(
            "thread-1", "PLAN\ninspect", True, None, False, "PLAN", True, "Astra", "codex", None
        ),
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("consult"))
    assert astra_advisor.main(["--bind", "--cwd", "."]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"] == "codex"
    assert payload["astra_enabled"] is True
    assert "sol_enabled" not in payload


def test_active_docs_use_astra_names() -> None:
    package_root = SCRIPTS_ROOT.parents[2]
    advisor_root = SCRIPTS_ROOT.parent
    all_paths = [
        advisor_root / "advisor-protocol.md",
        *sorted((advisor_root / "reference").glob("*.md")),
        package_root / ".agents" / "skills" / "team-advisor" / "SKILL.md",
        package_root / "docs" / "references" / "team-advisor-skill.md",
    ]
    legacy_names = ("ADVISOR_SOL", "--enable-sol", "codex_sol_advisor", "sol-rung.md")
    for each_path in all_paths:
        content = each_path.read_text(encoding="utf-8")
        assert all(name not in content for name in legacy_names)


def test_team_advisor_source_references_resolve_from_the_package_tree() -> None:
    package_root = SCRIPTS_ROOT.parents[2]
    skill_path = package_root / ".agents" / "skills" / "team-advisor" / "SKILL.md"
    all_reference_targets = (
        "../../../docs/references/advisor-tool.md",
        "../../../_shared/advisor/advisor-protocol.md",
        "../../../_shared/advisor/reference/third-party-bind.md",
        "../../../_shared/advisor/reference/astra-rung.md",
        "../../../_shared/advisor/reference/consult-format.md",
    )
    for each_target in all_reference_targets:
        assert (skill_path.parent / each_target).is_file(), each_target


def test_astra_docs_name_shared_effort_and_helper() -> None:
    advisor_root = SCRIPTS_ROOT.parent
    rung = (advisor_root / "reference" / "astra-rung.md").read_text(encoding="utf-8")
    protocol = (advisor_root / "advisor-protocol.md").read_text(encoding="utf-8")
    assert "ADVISOR_EFFORT" in rung
    assert "ADVISOR_ASTRA=1" in protocol
    assert "codex_astra_advisor.py" in rung
    assert "--resume <session_id>" in rung


BROKER_WAIT_EXIT_CODE = 3
BROKER_CLOCK = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
ROSTER_TEAM_NAME = "acct-team"
ROSTER_PLUS_NAME = "acct-plus"
UNREAD_REASON = "codex app-server did not answer"
BrokerBehavior = Callable[[list[str]], subprocess.CompletedProcess[str]]


class _Consultation(NamedTuple):
    reply: astra_advisor.CodexAstraAdvisorReply
    all_calls: list[list[str]]
    all_call_keywords: list[dict[str, object]]


def _reading(home: Path, plan_type: str | None, session_left: float, weekly_left: float) -> Reading:
    account = Account(Product.CODEX, home.name, home.resolve())
    return Reading(account, Meters(session_left, None, weekly_left, None, plan_type))


def _unreadable_reading(home: Path) -> Reading:
    return Reading(Account(Product.CODEX, home.name, home.resolve()), None, UNREAD_REASON)


def _roster_readings(tmp_path: Path) -> tuple[Reading, Reading]:
    return (
        _reading(tmp_path / ROSTER_TEAM_NAME, "team", 90.0, 95.0),
        _reading(tmp_path / ROSTER_PLUS_NAME, "plus", 60.0, 70.0),
    )


def _broker_completion(
    all_arguments: Sequence[str],
    all_roster_readings: Sequence[Reading],
    all_outside_readings: Sequence[Reading],
) -> subprocess.CompletedProcess[str]:
    reading_by_home: Mapping[Path, Reading] = {
        each_reading.account.home: each_reading
        for each_reading in (*all_roster_readings, *all_outside_readings)
    }
    if "--home" in all_arguments:
        exported_home = Path(all_arguments[all_arguments.index("--home") + 1]).resolve()
        all_readings = [reading_by_home[exported_home]]
    else:
        all_readings = list(all_roster_readings)
    required_tier = (
        all_arguments[all_arguments.index("--require-tier") + 1]
        if "--require-tier" in all_arguments
        else None
    )
    decision = choose_from_readings(
        Product.CODEX, all_readings, now=BROKER_CLOCK, required_tier=required_tier
    )
    answer = {
        "decision": decision_payload(decision),
        "accounts": readings_payload(all_readings),
    }
    exit_code = BROKER_WAIT_EXIT_CODE if decision.action == "wait" else 0
    return subprocess.CompletedProcess(list(all_arguments), exit_code, json.dumps(answer), "")


def _broker_exits_with_an_error(all_arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(all_arguments, 2, "", "bad roster")


def _broker_prints_text_that_is_not_json(
    all_arguments: list[str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(all_arguments, 0, "not json", "")


def _broker_times_out(all_arguments: list[str]) -> subprocess.CompletedProcess[str]:
    raise subprocess.TimeoutExpired(all_arguments, 150)


def _consult(
    tmp_path: Path,
    exported_home: str | None,
    all_outside_readings: Sequence[Reading] = (),
    broker_behavior: BrokerBehavior | None = None,
) -> _Consultation:
    all_calls: list[list[str]] = []
    all_call_keywords: list[dict[str, object]] = []
    all_roster_readings = _roster_readings(tmp_path)

    def answer_from_the_roster(all_arguments: list[str]) -> subprocess.CompletedProcess[str]:
        return _broker_completion(all_arguments, all_roster_readings, all_outside_readings)

    answer_broker = answer_from_the_roster if broker_behavior is None else broker_behavior

    def runner(all_arguments: list[str], **keywords: object) -> subprocess.CompletedProcess[str]:
        all_calls.append(all_arguments)
        all_call_keywords.append(keywords)
        if all_arguments[1] == str(BROKER_PATH):
            return answer_broker(all_arguments)
        return subprocess.CompletedProcess(all_arguments, 0, _events(), "")

    settings = (
        ENABLED_SETTINGS
        if exported_home is None
        else {**ENABLED_SETTINGS, "CODEX_HOME": exported_home}
    )
    reply = astra_advisor.run_codex_astra_advisor(
        "consult", Path("."), None, BROKER_PATH, settings, None, runner
    )
    return _Consultation(reply, all_calls, all_call_keywords)


def _assert_ran_on_the_exported_home(consultation: _Consultation, exported_home: Path) -> None:
    assert consultation.reply.successful
    codex_environment = consultation.all_call_keywords[1]["env"]
    assert isinstance(codex_environment, dict)
    assert codex_environment["CODEX_HOME"] == str(exported_home.resolve())
    assert consultation.all_calls[0] == [
        sys.executable, str(BROKER_PATH), "choose", "--product", "codex", "--home", str(exported_home),
    ]
    assert len(consultation.all_calls) == 2


def _assert_refused_without_a_launch(
    consultation: _Consultation, all_reason_parts: Sequence[str]
) -> None:
    assert consultation.reply.is_fallback
    assert not consultation.reply.successful
    assert consultation.reply.fallback_kind == astra_advisor.ASTRA_FALLBACK_KIND_DECLINED
    for each_reason_part in all_reason_parts:
        assert each_reason_part in (consultation.reply.reason or "")
    assert len(consultation.all_calls) == 1
    assert consultation.all_calls[0][1] == str(BROKER_PATH)


def test_should_run_on_a_paid_exported_home_that_is_in_the_roster(tmp_path: Path) -> None:
    exported_home = tmp_path / ROSTER_PLUS_NAME

    consultation = _consult(tmp_path, str(exported_home))

    _assert_ran_on_the_exported_home(consultation, exported_home)


def test_should_trim_the_padding_around_an_exported_home(tmp_path: Path) -> None:
    exported_home = tmp_path / ROSTER_PLUS_NAME

    consultation = _consult(tmp_path, f"  {exported_home}  ")

    _assert_ran_on_the_exported_home(consultation, exported_home)


def test_should_run_on_a_paid_exported_home_that_is_outside_the_roster(tmp_path: Path) -> None:
    exported_home = tmp_path / "outside-plus"

    consultation = _consult(tmp_path, str(exported_home), [_reading(exported_home, "plus", 80.0, 85.0)])

    _assert_ran_on_the_exported_home(consultation, exported_home)


def test_should_run_on_a_pro_exported_home_at_the_luna_tier(tmp_path: Path) -> None:
    exported_home = tmp_path / "acct-pro"
    pro_reading = _reading(exported_home, "pro", 5.0, 80.0)
    home_answer = json.loads(
        _broker_completion(
            ["--home", str(exported_home)], _roster_readings(tmp_path), [pro_reading]
        ).stdout
    )
    assert home_answer["decision"]["tier"] == "luna"

    consultation = _consult(tmp_path, str(exported_home), [pro_reading])

    _assert_ran_on_the_exported_home(consultation, exported_home)


def test_should_refuse_a_free_exported_home_when_a_roster_exists(tmp_path: Path) -> None:
    exported_home = tmp_path / "acct-free"

    consultation = _consult(tmp_path, str(exported_home), [_reading(exported_home, "free", 95.0, 95.0)])

    _assert_refused_without_a_launch(
        consultation, ["acct-free is on a free plan and is never chosen"]
    )


def test_should_refuse_an_unlisted_plan_exported_home_when_a_roster_exists(tmp_path: Path) -> None:
    exported_home = tmp_path / "acct-mystery"

    consultation = _consult(
        tmp_path, str(exported_home), [_reading(exported_home, "mystery", 95.0, 95.0)]
    )

    _assert_refused_without_a_launch(
        consultation, ["acct-mystery reports no known plan and is never chosen"]
    )


def test_should_refuse_an_unreadable_exported_home(tmp_path: Path) -> None:
    exported_home = tmp_path / "acct-unread"

    consultation = _consult(tmp_path, str(exported_home), [_unreadable_reading(exported_home)])

    _assert_refused_without_a_launch(consultation, ["acct-unread", UNREAD_REASON])


@pytest.mark.parametrize(
    "broker_behavior",
    [_broker_exits_with_an_error, _broker_prints_text_that_is_not_json, _broker_times_out],
)
def test_should_refuse_the_exported_home_when_the_broker_cannot_check_it(
    tmp_path: Path, broker_behavior: BrokerBehavior
) -> None:
    consultation = _consult(
        tmp_path, str(tmp_path / ROSTER_PLUS_NAME), broker_behavior=broker_behavior
    )

    assert consultation.reply.is_fallback
    assert consultation.reply.fallback_kind == astra_advisor.ASTRA_FALLBACK_KIND_BROKEN
    assert len(consultation.all_calls) == 1


@pytest.mark.parametrize("exported_home", [None, "", "   "])
def test_should_choose_from_the_roster_when_no_home_is_exported(
    tmp_path: Path, exported_home: str | None
) -> None:
    consultation = _consult(tmp_path, exported_home)

    assert consultation.reply.successful
    assert consultation.all_calls[0] == [
        sys.executable, str(BROKER_PATH), "choose", "--product", "codex", "--require-tier", "normal",
    ]
    codex_environment = consultation.all_call_keywords[1]["env"]
    assert isinstance(codex_environment, dict)
    assert codex_environment["CODEX_HOME"] == str((tmp_path / ROSTER_TEAM_NAME).resolve())
