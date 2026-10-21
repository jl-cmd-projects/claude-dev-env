"""Validate evidence-backed diagram scenes and render a portable HTML visual."""
import argparse
import copy
import json
import re
from pathlib import Path
from urllib.parse import quote

from metrics import prepare_chart, prepare_embedded_charts
from visual_config.config import constants as c


class RenderRunFatal(ValueError):
    """Stop rendering when scene structure or evidence is invalid."""


def _validate_drilldown(node: dict) -> None:
    flow = node.get("drilldown")
    if not flow or not flow.get("title") or not c.MINIMUM_DRILLDOWN_STEPS <= len(flow.get("steps", [])) <= c.MAXIMUM_DRILLDOWN_STEPS:
        raise RenderRunFatal("Every node needs a titled drilldown with two to six steps.")
    for each_step in flow["steps"]:
        if not each_step.get("label") or not each_step.get("icon"):
            raise RenderRunFatal("Every drilldown step needs a label and icon.")
    for each_edge in flow.get("edges", []):
        if not 0 <= each_edge["from"] < len(flow["steps"]) or not 0 <= each_edge["to"] < len(flow["steps"]) or each_edge["from"] == each_edge["to"]:
            raise RenderRunFatal("Invalid drilldown edge.")


def _validate_graph(scene: dict) -> None:
    node_ids = [each_node["id"] for each_node in scene["nodes"]]
    if len(set(node_ids)) != len(node_ids):
        raise RenderRunFatal("Duplicate diagram node IDs.")
    for each_edge in scene["edges"]:
        if each_edge["from"] not in node_ids or each_edge["to"] not in node_ids:
            raise RenderRunFatal("Edge refers to a missing node.")
        if not re.fullmatch(c.SVG_PATH_PATTERN, each_edge["path"]):
            raise RenderRunFatal("Invalid SVG path.")
    for each_node in scene["nodes"]:
        if not scene.get("chart") and (not c.MINIMUM_NODE_X <= each_node["x"] <= c.MAXIMUM_NODE_X or not c.MINIMUM_NODE_Y <= each_node["y"] <= c.MAXIMUM_NODE_Y):
            raise RenderRunFatal("Node lies outside diagram bounds.")
        if not each_node.get("sources"):
            raise RenderRunFatal("Every node needs source evidence.")
        _validate_drilldown(each_node)


def _source_evidence(source: dict, snapshot: dict, snapshot_path: Path) -> None:
    side = source.get("side", c.HEAD_SIDE)
    if side not in c.ALL_SOURCE_SIDES:
        raise RenderRunFatal("Source side must be head or base.")
    source_root = snapshot_path.parent / side
    source_path = (source_root / source["path"]).resolve()
    if not source_path.is_relative_to(source_root):
        raise RenderRunFatal("Source path leaves snapshot.")
    all_lines = source_path.read_text(encoding="utf-8-sig").splitlines()
    first, last = source["line"], source.get("end", source["line"])
    if not 1 <= first <= last <= len(all_lines):
        raise RenderRunFatal("Invalid source line range.")
    source["excerpt"] = c.NEWLINE.join(c.SOURCE_LINE.format(number=each_index + first, line=each_line) for each_index, each_line in enumerate(all_lines[first - 1:last]))
    if snapshot.get("kind") == c.ISSUE_KIND:
        source["url"] = _captured_record_link(source["path"], snapshot)
        return
    revision = snapshot.get("diff_base", snapshot[c.BASE_SIDE]) if side == c.BASE_SIDE else snapshot[c.HEAD_SIDE]
    source["url"] = c.SOURCE_LINK.format(repo=snapshot["repo"], revision=revision, path=quote(source["path"], safe="/"), first=first, last=last)


def _captured_record_link(relative_path: str, snapshot: dict) -> str:
    if matched_issue := re.fullmatch(c.CAPTURED_ISSUE_PATTERN, relative_path):
        return c.ISSUE_LINK.format(repo=snapshot["repo"], number=matched_issue.group(1))
    if matched_pull := re.fullmatch(c.CAPTURED_PULL_PATTERN, relative_path):
        return c.PULL_LINK.format(repo=snapshot["repo"], number=matched_pull.group(1))
    if relative_path == c.TRACKER_PATH:
        return snapshot["url"]
    raise RenderRunFatal("Tracker evidence must cite a captured issue, pull request, or tracker file.")


def _plain_title(record: dict, settings: dict) -> str:
    title = settings.get("titles", {}).get(str(record["number"]), record["title"])
    for each_pattern in settings.get("strip", []):
        title = re.sub(each_pattern, "", title, count=1)
    return title


def _open_task_entry(issue: dict, repo: str, settings: dict) -> dict:
    progress = issue["progress"]
    all_pulls = [each_pull for each_pull in issue["linked_pulls"] if (each_pull["merged_at"] if progress == "merged_pull" else each_pull["state"] == "open")]
    pulls = c.PULL_REFERENCE_SEPARATOR.join(c.PULL_REFERENCE.format(number=each_pull["number"]) for each_pull in all_pulls)
    return {
        "number": issue["number"],
        "title": _plain_title(issue, settings),
        "url": c.ISSUE_LINK.format(repo=repo, number=issue["number"]),
        "progress": progress,
        "status": c.ALL_REMAINING_STATUS[progress].format(pulls=pulls),
        "owner": settings.get("owners", {}).get(progress, c.DEFAULT_OWNER),
        "pulls": [{"number": each_pull["number"], "url": c.PULL_LINK.format(repo=repo, number=each_pull["number"])} for each_pull in all_pulls],
    }


def _remaining_groups(record: dict, repo: str, settings: dict) -> list[dict]:
    all_open_tasks = [each_child for each_child in record["children"] if not each_child["children"] and each_child["state"] == "open" and each_child["number"] not in settings.get("exclude", [])]
    all_open_tasks.sort(key=lambda each_task: c.ALL_PULL_PROGRESS[::-1].index(each_task["progress"]))
    all_groups = [{"number": record["number"], "title": _plain_title(record, settings), "url": c.ISSUE_LINK.format(repo=repo, number=record["number"]), "items": [_open_task_entry(each_task, repo, settings) for each_task in all_open_tasks]}] if all_open_tasks else []
    for each_child in record["children"]:
        all_groups.extend(_remaining_groups(each_child, repo, settings))
    return all_groups


def _extra_group(group: dict, snapshot: dict, snapshot_path: Path) -> dict:
    for each_listed_task in group["items"]:
        _source_evidence(each_listed_task["source"], snapshot, snapshot_path)
        each_listed_task.setdefault("url", each_listed_task["source"]["url"])
        if not each_listed_task["url"].startswith(c.REPOSITORY_LINK.format(repo=snapshot["repo"])):
            raise RenderRunFatal("A remaining item must link inside the tracked repository.")
    return group


def _prepare_remaining(scene: dict, snapshot: dict, snapshot_path: Path) -> None:
    """List every open task under its parent epic, then the scene's extra groups.

    A tracker scene gains a ``remaining`` list the viewer opens from its toolbar::

        Cert fixes          #12  Not started                            Theme team
                            #13  Fixed in pull request 20; still open    No owner named
        Follow-up branches  Image call counts  Waits to open           Theme team

    Args:
        scene: Scene with optional ``remaining`` settings: ``strip`` title
            prefix patterns, ``titles`` keyed by issue number for plain
            wording, ``owners`` keyed by pull progress, ``exclude``
            issue numbers that are not work items, and ``extra`` groups whose
            items cite a captured record.
        snapshot: Captured tracker snapshot.
        snapshot_path: Snapshot file the tracker tree sits beside.
    """
    settings = scene.get("remaining", {})
    tracker = json.loads((snapshot_path.parent / c.HEAD_SIDE / c.TRACKER_PATH).read_text(encoding="utf-8"))
    all_groups = _remaining_groups(tracker, snapshot["repo"], settings)
    all_groups.extend(_extra_group(each_group, snapshot, snapshot_path) for each_group in settings.get("extra", []))
    scene["remaining"] = {"groups": all_groups, "count": sum(len(each_group["items"]) for each_group in all_groups)}


def _prepare_sources(scene: dict, snapshot: dict, snapshot_path: Path) -> None:
    for each_node in scene["nodes"]:
        for each_source in each_node["sources"]:
            _source_evidence(each_source, snapshot, snapshot_path)


def prepare(path: Path) -> dict:
    """Bind a diagram to captured source and populate immutable evidence links.

    Args:
        path: Scene JSON path with a relative snapshot reference.

    Returns:
        The scene with PR identity, original summary, and source excerpts.

    Raises:
        RenderRunFatal: The scene or an evidence reference is invalid.
    """
    scene = json.loads(path.read_text(encoding="utf-8"))
    snapshot_path = (path.parent / scene["snapshot"]).resolve()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    scene["pr"] = {each_key: snapshot[each_key] for each_key in ("number", "url", "repo", "state", "head", "base", "observed_at")}
    is_issue = snapshot.get("kind") == c.ISSUE_KIND
    scene["pr"].update(kind=snapshot.get("kind", "pull"), draft=snapshot["metadata"]["draft"], merged=snapshot["metadata"].get("merged", False), changed_files=snapshot["metadata"]["tracked_issues"] if is_issue else len(snapshot["files"]), title=snapshot["metadata"]["title"])
    scene["summary"] = snapshot["metadata"]["body"] or "No PR description."
    _validate_graph(scene)
    _prepare_sources(scene, snapshot, snapshot_path)
    if is_issue:
        _prepare_remaining(scene, snapshot, snapshot_path)
    prepare_chart(scene, snapshot_path)
    prepare_embedded_charts(scene, snapshot_path)
    return scene


def _omit_private_payload(scene: dict) -> None:
    scene.pop("summary", None)
    for each_node in scene["nodes"]:
        for each_source in each_node["sources"]:
            each_source.pop("excerpt", None)
    for each_group in scene.get("remaining", {}).get("groups", []):
        for each_listed_task in each_group["items"]:
            each_listed_task.get("source", {}).pop("excerpt", None)


def render(all_scenes: list[dict], artifact_path: Path, is_links_only: bool = False) -> None:
    """Write a standalone interactive diagram or tabbed gallery.

    Args:
        all_scenes: Prepared diagrams with captured source evidence.
        artifact_path: Destination HTML file.
        is_links_only: Omit original descriptions and code excerpts.

    Raises:
        RenderRunFatal: The HTML exceeds the host size limit.
    """
    all_scenes = copy.deepcopy(all_scenes)
    if is_links_only:
        for each_scene in all_scenes:
            _omit_private_payload(each_scene)
    payload = json.dumps(all_scenes, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = c.VIEWER_PATH.read_text(encoding="utf-8")
    icons = c.ICONS_PATH.read_text(encoding="utf-8")
    rendered_html = template.replace("__ICONS__", icons).replace("__SCENES__", payload)
    if len(rendered_html.encode()) > c.MAXIMUM_HTML_BYTES:
        raise RenderRunFatal("HTML exceeds the host visualization limit.")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(rendered_html, encoding="utf-8")
    print(f"{artifact_path}: {len(all_scenes)} diagrams, {len(rendered_html.encode())} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenes", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--links-only", action="store_true", help="Omit original descriptions and code excerpts for hosted display.")
    arguments = parser.parse_args()
    render([prepare(each_path) for each_path in arguments.scenes], arguments.out, arguments.links_only)
