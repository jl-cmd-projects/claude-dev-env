import json
import subprocess
from collections.abc import Callable


def test_entry_point_registers_both_hook_groups(
    run_repository_command: Callable[[list[str]], subprocess.CompletedProcess[str]],
) -> None:
    script = (
        "import {register} from './packages/usage-wrapup/hooks/index.ts'; "
        "const events = []; "
        "register((event) => events.push(event), {}); "
        "console.log(JSON.stringify(events));"
    )
    registration_run = run_repository_command(["bun", "-e", script])

    assert json.loads(registration_run.stdout) == ["session.measure", "tool.call", "turn.complete"]
