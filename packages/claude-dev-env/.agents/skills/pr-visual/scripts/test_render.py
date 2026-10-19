"""Exercise numerical provenance, evidence boundaries, and portable rendering."""
import copy
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIRECTORY))
from metrics import MetricRunFatal, prepare_chart
from render import RenderRunFatal, _source_evidence, prepare, render

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FORMATS = ("flow", "bar", "line", "scatter")
EXPECTED_Y = [12, 20, 17]
INVALID_VALUES = (True, None, "12", float("nan"), float("inf"))


@pytest.mark.parametrize("kind", FORMATS)
def test_render_source_backed_format(kind: str, tmp_path: Path) -> None:
    """Every format retains immutable evidence and interactive detail data."""
    scene = prepare(FIXTURES / f"{kind}.scene.json")
    artifact_path = tmp_path / "visual.html"
    render([scene], artifact_path)
    assert "__SCENES__" not in artifact_path.read_text()
    assert scene["nodes"][0]["sources"][0]["url"].endswith("/metrics.json#L4-L5")
    if kind != "flow":
        assert [each_node["values"]["y"] for each_node in scene["nodes"]] == EXPECTED_Y


@pytest.mark.parametrize("value", INVALID_VALUES)
def test_chart_rejects_nonnumeric_measurements(value: object, tmp_path: Path) -> None:
    """Missing and nonnumeric observations cannot become plotted values."""
    scene = json.loads((FIXTURES / "bar.scene.json").read_text())
    (tmp_path / "head").mkdir()
    (tmp_path / "head/metrics.json").write_text(json.dumps({"samples": [{"duration_ms": value}]}))
    with pytest.raises(MetricRunFatal):
        prepare_chart(scene, tmp_path / "snapshot.json")


def test_missing_pointer_fails_instead_of_zero() -> None:
    """A missing observation cannot imply a zero measurement."""
    scene = prepare(FIXTURES / "bar.scene.json")
    scene["nodes"][0]["metrics"]["y"]["pointer"] = "/missing"
    with pytest.raises(MetricRunFatal):
        prepare_chart(scene, FIXTURES / "snapshot.json")


@pytest.mark.parametrize("source", [{"path": "../../outside", "line": 1}, {"path": "metrics.json", "line": 0}, {"path": "metrics.json", "line": 1, "side": "other"}])
def test_source_boundary_rejects_invalid_references(source: dict) -> None:
    """Evidence must remain inside a captured side and a valid line range."""
    snapshot = json.loads((FIXTURES / "snapshot.json").read_text())
    with pytest.raises(RenderRunFatal):
        _source_evidence(source, snapshot, FIXTURES / "snapshot.json")


def test_links_only_is_private_and_does_not_mutate_scene(tmp_path: Path) -> None:
    """Hosted output drops payload excerpts without modifying the prepared scene."""
    scene = prepare(FIXTURES / "flow.scene.json")
    original = copy.deepcopy(scene)
    artifact_path = tmp_path / "visual.html"
    render([scene], artifact_path, is_links_only=True)
    payload = artifact_path.read_text().split("data-scenes>", 1)[1].split("</script>", 1)[0]
    public = json.loads(payload)[0]
    assert "summary" not in public
    assert all("excerpt" not in each_source for each_node in public["nodes"] for each_source in each_node["sources"])
    assert scene == original


def test_embedded_text_cannot_close_script(tmp_path: Path) -> None:
    """Captured prose remains data even when it contains HTML closing tags."""
    scene = prepare(FIXTURES / "flow.scene.json")
    scene["summary"] = "</script><script>window.untrusted=1</script>"
    artifact_path = tmp_path / "visual.html"
    render([scene], artifact_path)
    assert scene["summary"] not in artifact_path.read_text()
