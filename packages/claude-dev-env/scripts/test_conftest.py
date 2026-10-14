from pathlib import Path

import account_broker
import account_broker_support

_user_home_at_import = Path.home()


def test_isolated_broker_state_path_redirects_every_bound_resolver(
    isolated_broker_state_path: Path, tmp_path: Path
) -> None:
    assert isolated_broker_state_path.is_relative_to(tmp_path)
    assert not isolated_broker_state_path.is_relative_to(_user_home_at_import)
    assert account_broker_support.broker_state_path() == isolated_broker_state_path
    assert account_broker.broker_state_path() == isolated_broker_state_path
