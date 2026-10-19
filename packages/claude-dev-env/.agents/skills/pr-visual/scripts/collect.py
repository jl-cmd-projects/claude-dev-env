"""Capture PR metadata, patches, and immutable changed-file source through gh."""
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="+")
    parser.add_argument("--out", type=Path, default=Path(c.DEFAULT_EVIDENCE_DIRECTORY))
    arguments = parser.parse_args()
    for each_url in arguments.urls:
        collect(each_url, arguments.out)
