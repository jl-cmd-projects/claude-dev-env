import subprocess
from collections.abc import Callable


def test_plugin_state_declares_compacted_windows(
    run_from_repository_root: Callable[[list[str]], subprocess.CompletedProcess[str]],
) -> None:
    plugin_validation_run = run_from_repository_root(
        ["claude", "plugin", "validate", "packages/usage-wrapup"]
    )

    assert (
        "types ./types/index.d.ts declares state: usage-wrapup.compacted"
        in plugin_validation_run.stdout
    ), plugin_validation_run.stdout
