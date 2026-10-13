from collections.abc import Callable
from pathlib import Path

import account_broker_support


def test_isolated_broker_state_path_redirects_the_module_resolver(
    isolated_broker_state_path: Path, tmp_path: Path
) -> None:
    assert isolated_broker_state_path == tmp_path / "account-broker" / "state.json"
    assert account_broker_support.broker_state_path() == isolated_broker_state_path


def test_create_directory_link_exposes_the_target_contents(
    create_directory_link: Callable[..., None], tmp_path: Path
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "entry.txt").write_text("linked content", encoding="utf-8")
    link = tmp_path / "link"

    create_directory_link(from_link=link, to_target=target)

    assert (link / "entry.txt").read_text(encoding="utf-8") == "linked content"
