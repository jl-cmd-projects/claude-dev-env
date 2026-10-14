import sys
from pathlib import Path

flow_directory = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(flow_directory), str(flow_directory.parent / "features-start-with-an-eval")]

from rules_eval_support.launch import _read_events, launch_words


def test_launch_words_preserves_the_command_in_both_modes() -> None:
    command = ["claude", "-p", "case prompt"]

    assert launch_words(Path("report.json"), command, is_direct=True)[1:] == command[1:]
    assert launch_words(Path("report.json"), command, is_direct=False)[-3:] == command


def test_read_events_skips_invalid_lines_and_non_objects(tmp_path: Path) -> None:
    stream = tmp_path / "stream.jsonl"
    stream.write_text('invalid\n[]\n{"type": "result"}\n', encoding="utf-8")

    assert _read_events(stream) == [{"type": "result"}]
