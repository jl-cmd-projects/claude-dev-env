from hooks_constants import subagent_model_gate_constants as constants


def test_gate_denies_the_sonnet_and_fable_aliases() -> None:
    assert constants.ALL_DENIED_MODEL_ALIASES == frozenset({"sonnet", "fable"})


def test_gate_denies_full_sonnet_and_fable_ids_by_prefix() -> None:
    assert constants.ALL_DENIED_MODEL_ID_PREFIXES == ("claude-sonnet", "claude-fable")


def test_gate_checks_the_agent_and_task_spawn_tools() -> None:
    assert constants.ALL_CHECKED_TOOL_NAMES == frozenset({"Agent", "Task"})


def test_gate_exit_codes_match_the_hook_contract() -> None:
    assert (constants.ALLOW_EXIT_CODE, constants.BLOCK_EXIT_CODE) == (0, 2)
