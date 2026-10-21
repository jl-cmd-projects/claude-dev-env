"""Exercise numerical provenance, evidence boundaries, and portable rendering."""
import copy
import json
import shutil
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


def test_tracker_scene_links_each_record_to_its_issue_or_pull_request(tmp_path: Path) -> None:
    """Tracker evidence opens the issue or pull request a captured record came from."""
    scene = prepare(FIXTURES / "tracker.scene.json")
    render([scene], tmp_path / "visual.html")
    all_links = [each_source["url"] for each_node in scene["nodes"] for each_source in each_node["sources"]]
    assert all_links == ["https://github.com/example/project/issues/1", "https://github.com/example/project/issues/2", "https://github.com/example/project/pull/3", "https://github.com/example/project/issues/1"]
    assert scene["pr"]["kind"] == "issue"
    assert scene["pr"]["changed_files"] == 3


def test_tracker_scene_rejects_evidence_outside_captured_records(tmp_path: Path) -> None:
    """A tracker source must name a captured issue, pull request, or the tracker tree."""
    tracker_copy = tmp_path / "tracker"
    shutil.copytree(FIXTURES / "tracker", tracker_copy)
    (tracker_copy / "head/notes.txt").write_text("synthetic\n")
    snapshot = json.loads((tracker_copy / "snapshot.json").read_text())
    with pytest.raises(RenderRunFatal, match="Tracker evidence"):
        _source_evidence({"path": "notes.txt", "line": 1}, snapshot, tracker_copy / "snapshot.json")


def test_tracker_scene_lists_every_open_task_under_its_epic(tmp_path: Path) -> None:
    """Each open task appears once under its epic with its status, owner, and issue link."""
    scene = prepare(FIXTURES / "tracker.scene.json")
    render([scene], tmp_path / "visual.html", is_links_only=True)
    epic, follow_ups = scene["remaining"]["groups"]
    assert [(each_item["number"], each_item["title"], each_item["status"], each_item["owner"]) for each_item in epic["items"]] == [
        (4, "task without a fix", "Not started", "Build team"),
        (2, "task with a fix", "Fixed in pull request 3; the issue is still open", "Tracker cleanup"),
    ]
    assert epic["items"][1]["url"] == "https://github.com/example/project/issues/2"
    assert follow_ups["items"][0]["url"] == "https://github.com/example/project/issues/1"
    assert scene["remaining"]["count"] == 3
    assert "Task one ships" not in (tmp_path / "visual.html").read_text()


def test_tracker_extra_item_rejects_a_link_outside_the_repository(tmp_path: Path) -> None:
    """An extra remaining item cannot point away from the tracked repository."""
    scene_copy = tmp_path / "tracker.scene.json"
    shutil.copytree(FIXTURES / "tracker", tmp_path / "tracker")
    scene = json.loads((FIXTURES / "tracker.scene.json").read_text())
    scene["remaining"]["extra"][0]["items"][0]["url"] = "https://example.com/elsewhere"
    scene_copy.write_text(json.dumps(scene))
    with pytest.raises(RenderRunFatal, match="tracked repository"):
        prepare(scene_copy)


def test_tracker_scene_leaves_out_excluded_issues(tmp_path: Path) -> None:
    """An issue the scene names as not a work item stays off the remaining list."""
    shutil.copytree(FIXTURES / "tracker", tmp_path / "tracker")
    scene = json.loads((FIXTURES / "tracker.scene.json").read_text())
    scene["remaining"]["exclude"] = [4]
    (tmp_path / "tracker.scene.json").write_text(json.dumps(scene))
    epic = prepare(tmp_path / "tracker.scene.json")["remaining"]["groups"][0]
    assert [each_item["number"] for each_item in epic["items"]] == [2]


def test_tracker_scene_uses_the_plain_title_a_scene_gives(tmp_path: Path) -> None:
    """The list shows the plain title a scene gives for an issue number."""
    shutil.copytree(FIXTURES / "tracker", tmp_path / "tracker")
    scene = json.loads((FIXTURES / "tracker.scene.json").read_text())
    scene["remaining"]["titles"] = {"4": "Build the missing fix"}
    (tmp_path / "tracker.scene.json").write_text(json.dumps(scene))
    epic = prepare(tmp_path / "tracker.scene.json")["remaining"]["groups"][0]
    assert [each_entry["title"] for each_entry in epic["items"]] == ["Build the missing fix", "task with a fix"]
