"""Validate evidence-backed diagram scenes and render a portable HTML visual."""
import argparse
import copy
import itertools
import json
import re
from collections import Counter
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
        if not scene.get("chart") and not scene.get("board") and (not c.MINIMUM_NODE_X <= each_node["x"] <= c.MAXIMUM_NODE_X or not c.MINIMUM_NODE_Y <= each_node["y"] <= c.MAXIMUM_NODE_Y):
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


def _issue_steps(number: int, snapshot_path: Path, settings: dict) -> list[dict]:
    all_lines = (snapshot_path.parent / c.HEAD_SIDE / c.ISSUE_BODY_PATH.format(number=number)).read_text(encoding="utf-8").splitlines()
    all_steps = []
    for each_step in settings.get("steps", []):
        heading = c.SECTION_HEADING.format(heading=each_step["heading"])
        if heading not in all_lines:
            continue
        all_paragraph_lines = list(itertools.takewhile(str.strip, all_lines[all_lines.index(heading) + 1:]))
        text = c.SPACE_SEPARATOR.join(all_paragraph_lines)
        for each_word, each_plain_word in settings.get("wording", {}).items():
            text = re.sub(c.WHOLE_PHRASE_PATTERN.format(phrase=re.escape(each_word)), each_plain_word, text)
        all_steps.append({**{each_field: each_setting for each_field, each_setting in each_step.items() if each_field != "heading"}, "text": text})
    return all_steps


def _tracker_card(issue: dict, repo: str, settings: dict, snapshot_path: Path) -> dict:
    progress = issue["progress"]
    all_pulls = [each_pull for each_pull in issue["linked_pulls"] if (each_pull["merged_at"] if progress == "merged_pull" else each_pull["state"] == "open")]
    pulls = c.PULL_REFERENCE_SEPARATOR.join(c.PULL_REFERENCE.format(number=each_pull["number"]) for each_pull in all_pulls)
    return {
        "number": issue["number"],
        "title": _plain_title(issue, settings),
        "url": c.ISSUE_LINK.format(repo=repo, number=issue["number"]),
        "note": c.ALL_CARD_NOTES[progress].format(pulls=pulls),
        "steps": _issue_steps(issue["number"], snapshot_path, settings),
    }


def _tracker_groups(record: dict, progress: str, repo: str, settings: dict, snapshot_path: Path) -> list[dict]:
    all_tasks = [each_child for each_child in record["children"] if not each_child["children"] and each_child["state"] == "open" and each_child["progress"] == progress and each_child["number"] not in settings.get("exclude", [])]
    all_groups = [{"title": _plain_title(record, settings), "url": c.ISSUE_LINK.format(repo=repo, number=record["number"]), "cards": [_tracker_card(each_task, repo, settings, snapshot_path) for each_task in all_tasks]}] if all_tasks else []
    for each_child in record["children"]:
        all_groups.extend(_tracker_groups(each_child, progress, repo, settings, snapshot_path))
    return all_groups


def _cited_group(group: dict, snapshot: dict, snapshot_path: Path) -> dict:
    for each_card in group["cards"]:
        _source_evidence(each_card["source"], snapshot, snapshot_path)
        each_card.setdefault("url", each_card["source"]["url"])
        each_card.setdefault("note", "")
        if not each_card["url"].startswith(c.REPOSITORY_LINK.format(repo=snapshot["repo"])):
            raise RenderRunFatal("A board card must link inside the tracked repository.")
    group.setdefault("url", snapshot["url"])
    return group


def _board_lane(lane: dict, tracker: dict, settings: dict, snapshot: dict, snapshot_path: Path) -> dict:
    if "progress" in lane:
        all_groups = _tracker_groups(tracker, lane["progress"], snapshot["repo"], settings, snapshot_path)
    else:
        all_groups = [_cited_group(each_group, snapshot, snapshot_path) for each_group in lane.get("groups", [])]
    return {"node": lane["node"], "groups": all_groups, "count": sum(len(each_group["cards"]) for each_group in all_groups)}


def _prepare_board(scene: dict, snapshot: dict, snapshot_path: Path) -> None:
    """Place every tracker card in the state lane its scene names.

    The flow runs top to bottom. Each lane is one state node with its cards
    beside it, grouped under their parent epic::

        (Not started)   Convert . 2     [task 12]  [task 13]
              |
        (Fixed)         Icons . 1       [task 14  Merged in pull request 20]

    Args:
        scene: Scene with ``board`` settings: ``lanes`` in flow order, each
            naming a scene ``node`` and either a tracker ``progress``
            (``no_pull``, ``open_pull``, ``merged_pull``) or cited ``groups``
            of cards; ``strip`` title prefix patterns, ``titles`` keyed by
            issue number, ``exclude`` issue numbers that are not work,
            ``steps`` naming the body sections each card diagram shows,
            and ``wording`` swaps for that text.
        snapshot: Captured tracker snapshot.
        snapshot_path: Snapshot file the tracker tree sits beside.

    Raises:
        RenderRunFatal: A node lacks exactly one lane, or a card leaves the repository.
    """
    settings = scene["board"]
    tracker = json.loads((snapshot_path.parent / c.HEAD_SIDE / c.TRACKER_PATH).read_text(encoding="utf-8"))
    if sorted(each_lane["node"] for each_lane in settings["lanes"]) != sorted(each_node["id"] for each_node in scene["nodes"]):
        raise RenderRunFatal("Every board node needs exactly one lane.")
    all_lanes = [_board_lane(each_lane, tracker, settings, snapshot, snapshot_path) for each_lane in settings["lanes"]]
    scene["board"] = {"lanes": all_lanes, "count": sum(each_lane["count"] for each_lane in all_lanes)}
    require_own_card_content(scene["board"])


def require_own_card_content(board: dict) -> None:
    """Refuse a board whose cards say nothing of their own.

    A card passes when one of its steps carries text that is not its title
    or note and that no other card on the board repeats. A card holding only
    a title, a link, or text shared by every card in its lane fails.

    Args:
        board: Prepared board with ``lanes`` of ``groups`` of ``cards``.

    Raises:
        RenderRunFatal: Names each card with no content of its own.
    """
    all_cards = [each_card for each_lane in board["lanes"] for each_group in each_lane["groups"] for each_card in each_group["cards"]]
    text_counts = Counter(each_text for each_card in all_cards for each_text in _step_texts(each_card))
    all_empty_titles = [each_card["title"] for each_card in all_cards if not _has_own_step(each_card, text_counts)]
    if all_empty_titles:
        raise RenderRunFatal(c.EMPTY_CARD_MESSAGE.format(count=len(all_empty_titles), total=len(all_cards), titles=c.PULL_REFERENCE_SEPARATOR.join(all_empty_titles[:c.EMPTY_CARD_TITLE_LIMIT])))


def _step_texts(card: dict) -> set[str]:
    return {each_step.get("text", "").strip() for each_step in card.get("steps", [])}


def _has_own_step(card: dict, text_counts: Counter) -> bool:
    all_borrowed_text = {card["title"].strip(), card.get("note", "").strip(), ""}
    return any(text_counts[each_text] == 1 and each_text not in all_borrowed_text for each_text in _step_texts(card))


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
    if is_issue and scene.get("board"):
        _prepare_board(scene, snapshot, snapshot_path)
    prepare_chart(scene, snapshot_path)
    prepare_embedded_charts(scene, snapshot_path)
    return scene


def _omit_private_payload(scene: dict) -> None:
    scene.pop("summary", None)
    for each_node in scene["nodes"]:
        for each_source in each_node["sources"]:
            each_source.pop("excerpt", None)
    for each_lane in scene.get("board", {}).get("lanes", []):
        for each_group in each_lane["groups"]:
            for each_card in each_group["cards"]:
                each_card.get("source", {}).pop("excerpt", None)


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
