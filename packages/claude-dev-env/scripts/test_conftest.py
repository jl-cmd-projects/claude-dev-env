from pathlib import Path

import account_broker_support


def test_isolated_broker_state_path_resolves_under_tmp_path(
    isolated_broker_state_path: Path, tmp_path: Path
) -> None:
    assert isolated_broker_state_path.is_relative_to(tmp_path)
    assert account_broker_support.broker_state_path() == isolated_broker_state_path
