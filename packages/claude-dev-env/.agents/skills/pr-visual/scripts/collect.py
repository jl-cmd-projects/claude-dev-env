"""Capture PR source or tracker issue records as immutable evidence through gh."""
import argparse
import base64
import concurrent.futures
import datetime
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import quote

from visual_config.config import constants as c


class CaptureRunFatal(ValueError):
    """Stop capture when the PR moves or its source is incomplete."""


def _api(endpoint: str, *options: str) -> dict | list:
    completed = subprocess.run(["gh", "api", endpoint, *options], capture_output=True, text=True, check=False)
    if completed.returncode:
        raise CaptureRunFatal(completed.stderr.strip())
    return json.loads(completed.stdout)


def _changed_files(repo: str, number: str, expected_count: int) -> list[dict]:
    all_files = []
    page = 1
    while True:
        batch = _api(c.FILES_ENDPOINT.format(repo=repo, number=number, size=c.PAGE_SIZE, page=page))
        all_files.extend(batch)
        if len(batch) < c.PAGE_SIZE:
            break
        page += 1
    if len(all_files) != expected_count:
        raise CaptureRunFatal("Changed-file list is incomplete.")
    return all_files


def _capture_side(item: dict, side: str, metadata: dict, diff_base: str, destination: Path) -> dict:
    relative_path = item.get("previous_filename", item["filename"]) if side == c.BASE_SIDE else item["filename"]
    revision = diff_base if side == c.BASE_SIDE else metadata[c.HEAD_SIDE]["sha"]
    endpoint = c.CONTENTS_ENDPOINT.format(repo=metadata[side]["repo"]["full_name"], path=quote(relative_path, safe="/"), revision=revision)
    blob = _api(endpoint)
    if blob.get("encoding") != "base64":
        raise CaptureRunFatal(f"Source unavailable for {relative_path}. Fetch the Git blob before proceeding.")
    raw_bytes = base64.b64decode(blob["content"])
    source_path = (destination / side / relative_path).resolve()
    if not source_path.is_relative_to((destination / side).resolve()):
        raise CaptureRunFatal("Source path leaves snapshot.")
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(raw_bytes)
    return {"path": str(source_path.relative_to(destination.resolve())), "sha256": hashlib.sha256(raw_bytes).hexdigest(), "bytes": len(raw_bytes)}


def _capture_file(item: dict, metadata: dict, diff_base: str, destination: Path) -> dict:
    captures = {}
    for each_side in c.ALL_SOURCE_SIDES:
        if each_side == c.HEAD_SIDE and item["status"] == "removed":
            continue
        if each_side == c.BASE_SIDE and item["status"] == "added":
            continue
        captures[each_side] = _capture_side(item, each_side, metadata, diff_base, destination)
    return {**item, "captures": captures}


def _save_snapshot(snapshot: dict, destination: Path) -> None:
    (destination / c.SNAPSHOT_NAME).write_text(json.dumps(snapshot, indent=c.JSON_INDENT), encoding="utf-8")
    if snapshot.get("kind") == c.ISSUE_KIND:
        all_sections = []
    else:
        all_sections = [c.DIFF_SECTION.format(filename=each_file["filename"], patch=each_file.get("patch", "Patch unavailable. Compare saved base and head source.")) for each_file in snapshot["files"]]
    (destination / c.DIFF_NAME).write_text(c.PARAGRAPH_BREAK.join(all_sections), encoding="utf-8")
    print(json.dumps({"pr": snapshot["number"], "snapshot": str(destination / c.SNAPSHOT_NAME), "state": snapshot["state"], "files": len(snapshot["files"])}), flush=True)


def collect(url: str, root: Path) -> None:
    """Save the PR description, patches, and immutable source snapshot.

    Args:
        url: GitHub pull request URL.
        root: Directory receiving a folder for the captured head.

    Raises:
        CaptureRunFatal: Source is incomplete or the PR changes during capture.
    """
    matched_url = re.fullmatch(c.PR_URL_PATTERN, url)
    if not matched_url:
        raise CaptureRunFatal("Use a GitHub PR URL, https://github.com/owner/repo/pull/number")
    repo, number = matched_url.groups()
    endpoint = c.PR_ENDPOINT.format(repo=repo, number=number)
    metadata = _api(endpoint)
    compared = _api(c.COMPARE_ENDPOINT.format(repo=repo, base=metadata[c.BASE_SIDE]["sha"], head=metadata[c.HEAD_SIDE]["sha"]), "--jq", "{merge_base_commit: .merge_base_commit}")
    diff_base = compared["merge_base_commit"]["sha"]
    destination = root / f"pr-{number}" / metadata[c.HEAD_SIDE]["sha"]
    destination.mkdir(parents=True, exist_ok=True)
    all_files = _changed_files(repo, number, metadata["changed_files"])
    with concurrent.futures.ThreadPoolExecutor(max_workers=c.SOURCE_WORKERS) as pool:
        captured = list(pool.map(lambda each_file: _capture_file(each_file, metadata, diff_base, destination), all_files))
    refreshed = _api(endpoint)
    if any(refreshed[each_side]["sha"] != metadata[each_side]["sha"] for each_side in c.ALL_SOURCE_SIDES):
        raise CaptureRunFatal("PR changed during capture. Rerun collection.")
    snapshot = {"schema_version": 1, "observed_at": datetime.datetime.now(datetime.UTC).isoformat(), "repo": repo, "number": int(number), "url": url, "state": refreshed["state"], "head": metadata[c.HEAD_SIDE]["sha"], "base": metadata[c.BASE_SIDE]["sha"], "diff_base": diff_base, "metadata": refreshed, "files": captured}
    _save_snapshot(snapshot, destination)


def _sub_issues(repo: str, number: int) -> list[dict]:
    all_children = []
    page = 1
    while True:
        batch = _api(c.SUB_ISSUES_ENDPOINT.format(repo=repo, number=number, size=c.PAGE_SIZE, page=page))
        all_children.extend(batch)
        if len(batch) < c.PAGE_SIZE:
            break
        page += 1
    return all_children


def _write_capture(destination: Path, relative_path: str, raw_bytes: bytes) -> dict:
    capture_path = destination / c.HEAD_SIDE / relative_path
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    capture_path.write_bytes(raw_bytes)
    return {"filename": relative_path, "captures": {c.HEAD_SIDE: {"path": f"{c.HEAD_SIDE}/{relative_path}", "sha256": hashlib.sha256(raw_bytes).hexdigest(), "bytes": len(raw_bytes)}}}


def _json_bytes(record: dict) -> bytes:
    return (json.dumps(record, indent=c.JSON_INDENT) + c.NEWLINE).encode()


def _pull_progress(record: dict) -> str:
    all_pulls = record["linked_pulls"]
    if any(each_pull["merged_at"] for each_pull in all_pulls):
        return "merged_pull"
    if any(each_pull["state"] == "open" for each_pull in all_pulls):
        return "open_pull"
    return "no_pull"


def _child_counts(all_children: list[dict]) -> dict[str, int]:
    all_progress = [each_child["progress"] for each_child in all_children]
    return {
        "open": sum(each_child["state"] == "open" for each_child in all_children),
        "closed": sum(each_child["state"] == "closed" for each_child in all_children),
        **{each_progress: all_progress.count(each_progress) for each_progress in c.ALL_PULL_PROGRESS},
    }


def _capture_issue_tree(repo: str, issue: dict, depth: int, all_pulls_by_number: dict[int, dict], destination: Path, all_files: list[dict]) -> dict:
    record = {each_field: issue.get(each_field) for each_field in c.ALL_ISSUE_FIELDS}
    record["labels"] = [each_label["name"] for each_label in issue.get("labels", [])]
    body = issue.get("body") or ""
    linked_numbers = sorted({int(each_number) for each_number in re.findall(c.LINKED_PULL_PATTERN.format(repo=re.escape(repo)), body)})
    for each_number in linked_numbers:
        if each_number not in all_pulls_by_number:
            pull = _api(c.PR_ENDPOINT.format(repo=repo, number=each_number))
            all_pulls_by_number[each_number] = {each_field: pull.get(each_field) for each_field in c.ALL_PULL_FIELDS}
    record["linked_pulls"] = [all_pulls_by_number[each_number] for each_number in linked_numbers]
    record["progress"] = _pull_progress(record)
    children = _sub_issues(repo, issue["number"]) if depth < c.SUB_ISSUE_DEPTH else []
    record["children"] = [_capture_issue_tree(repo, each_child, depth + 1, all_pulls_by_number, destination, all_files) for each_child in children]
    record["counts"] = _child_counts(record["children"])
    all_files.append(_write_capture(destination, c.ISSUE_BODY_PATH.format(number=issue["number"]), (body + c.NEWLINE).encode()))
    issue_record = {each_field: each_entry for each_field, each_entry in record.items() if each_field != "children"}
    all_files.append(_write_capture(destination, c.ISSUE_RECORD_PATH.format(number=issue["number"]), _json_bytes(issue_record)))
    return record


def _capture_tracker(repo: str, issue: dict, destination: Path) -> tuple[bytes, list[dict]]:
    all_files: list[dict] = []
    all_pulls_by_number: dict[int, dict] = {}
    tracker_bytes = _json_bytes(_capture_issue_tree(repo, issue, 0, all_pulls_by_number, destination, all_files))
    for each_number, each_pull in all_pulls_by_number.items():
        all_files.append(_write_capture(destination, c.PULL_RECORD_PATH.format(number=each_number), _json_bytes(each_pull)))
    all_files.append(_write_capture(destination, c.TRACKER_PATH, tracker_bytes))
    return tracker_bytes, all_files


def _tracker_snapshot(url: str, repo: str, refreshed: dict, observed_at: str, tracker_bytes: bytes, all_files: list[dict]) -> dict:
    tracked_count = sum(1 for each_file in all_files if re.fullmatch(c.CAPTURED_ISSUE_RECORD_PATTERN, each_file["filename"]))
    metadata = {"title": refreshed["title"], "body": refreshed.get("body") or "", "draft": False, "merged": False, "tracked_issues": tracked_count}
    return {"schema_version": 1, "kind": c.ISSUE_KIND, "observed_at": observed_at, "repo": repo, "number": refreshed["number"], "url": url, "state": refreshed["state"], "head": hashlib.sha256(tracker_bytes).hexdigest(), "base": None, "diff_base": None, "metadata": metadata, "files": all_files}


def collect_issue(url: str, root: Path) -> None:
    """Save an issue, its sub-issues, and the pull requests their bodies link.

    A tracker epic becomes the same kind of snapshot a pull request does::

        issues/12.md      the issue body, line by line
        issues/12.json    state, labels, linked pull requests, child counts
        pulls/34.json     each linked pull request's state
        tracker.json      the whole tree, for charts and citations

    Args:
        url: GitHub issue URL.
        root: Directory receiving a folder for the captured issue.

    Raises:
        CaptureRunFatal: The issue changed during capture.
    """
    matched_url = re.fullmatch(c.ISSUE_URL_PATTERN, url)
    if not matched_url:
        raise CaptureRunFatal("Use a GitHub issue URL, https://github.com/owner/repo/issues/number")
    repo, number = matched_url.groups()
    endpoint = c.ISSUE_ENDPOINT.format(repo=repo, number=number)
    issue = _api(endpoint)
    observed_at = datetime.datetime.now(datetime.UTC).isoformat()
    destination = root / f"issue-{number}" / observed_at.replace(":", "-")
    tracker_bytes, all_files = _capture_tracker(repo, issue, destination)
    refreshed = _api(endpoint)
    if refreshed["updated_at"] != issue["updated_at"]:
        raise CaptureRunFatal("Issue changed during capture. Rerun collection.")
    _save_snapshot(_tracker_snapshot(url, repo, refreshed, observed_at, tracker_bytes, all_files), destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="+")
    parser.add_argument("--out", type=Path, default=Path(c.DEFAULT_EVIDENCE_DIRECTORY))
    arguments = parser.parse_args()
    for each_url in arguments.urls:
        if re.fullmatch(c.ISSUE_URL_PATTERN, each_url):
            collect_issue(each_url, arguments.out)
        else:
            collect(each_url, arguments.out)
