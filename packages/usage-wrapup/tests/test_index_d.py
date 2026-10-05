import subprocess
from pathlib import Path


def test_plugin_state_declares_compacted_windows() -> None:
    root = Path(__file__).resolve().parents[3]
    plugin_validation_run = subprocess.run(
        ["claude", "plugin", "validate", "packages/usage-wrapup"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "types ./types/index.d.ts declares state: usage-wrapup.compacted" in plugin_validation_run.stdout
