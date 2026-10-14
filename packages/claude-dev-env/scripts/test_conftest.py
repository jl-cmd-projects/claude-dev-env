from pathlib import Path


def test_isolated_broker_state_path_resolves_under_the_redirected_home(
    isolated_broker_state_path: Path, tmp_path: Path
) -> None:
    assert Path.home().is_relative_to(tmp_path)
    assert isolated_broker_state_path.is_relative_to(Path.home())
