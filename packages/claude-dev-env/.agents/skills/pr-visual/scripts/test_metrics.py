"""Verify embedded chart provenance and passive Python literal extraction."""
import copy
import sys
from pathlib import Path

import pytest

SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from metrics import MetricRunFatal, _coordinate, prepare_embedded_charts
from render import prepare

FIXTURES = SCRIPTS_DIRECTORY.parents[0] / "fixtures"
ALL_LITERAL_CASES = (("assert metric == 2.0", {}, 2.0), ("Pair(90, 180)", {"argument": 1}, 180), ("peaks = (1, 2, 10)", {"element": 2}, 10))


@pytest.mark.parametrize("source_text,selector,expected", ALL_LITERAL_CASES)
def test_numeric_literals_are_read_without_executing_source(source_text: str, selector: dict, expected: float, tmp_path: Path) -> None:
    """Executable statements in the source remain inert during chart preparation."""
    source_root = tmp_path / "head"
    source_root.mkdir()
    (source_root / "example.py").write_text('raise RuntimeError("Source must remain inert")\n' + source_text + "\n")
    node = {"sources": [{"path": "example.py", "line": 2}]}
    assert _coordinate({"source": 0, "python_line": 2, **selector}, node, tmp_path / "snapshot.json") == expected


def test_embedded_summary_and_node_chart_share_reviewed_values() -> None:
    """The overview card and detail card use the same captured fixture data."""
    scene = prepare(FIXTURES / "integrated.scene.json")
    assert scene["summary_chart"]["points"] == scene["nodes"][0]["chart"]["points"]
    assert [each_point["values"]["y"] for each_point in scene["summary_chart"]["points"]] == [12, 20, 17]


def test_ungrounded_embedded_numbers_are_rejected() -> None:
    """Author-entered chart coordinates cannot replace source references."""
    scene = copy.deepcopy(prepare(FIXTURES / "integrated.scene.json"))
    scene["summary_chart"]["points"][0].pop("metrics")
    with pytest.raises(MetricRunFatal):
        prepare_embedded_charts(scene, FIXTURES / "snapshot.json")


def test_python_numbers_outside_cited_lines_are_rejected(tmp_path: Path) -> None:
    """A measurement must be covered by its displayed evidence link."""
    (tmp_path / "head").mkdir()
    (tmp_path / "head/example.py").write_text("assert metric == 2\nassert metric == 10\n")
    with pytest.raises(MetricRunFatal, match="outside"):
        _coordinate({"source": 0, "python_line": 2}, {"sources": [{"path": "example.py", "line": 1}]}, tmp_path / "snapshot.json")
