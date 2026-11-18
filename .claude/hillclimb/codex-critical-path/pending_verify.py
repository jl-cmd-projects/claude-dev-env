"""Verify pending-command evidence and prepare anonymous grading packets."""

import argparse
import json
import secrets
import subprocess
import tarfile
from collections import Counter
from pathlib import Path
from statistics import median

import design_slice_proof
import pending_replay as runner
import design_slice_run
from pivot_proof import (
    BOOL_FIELDS, check_trace, finite_seconds, optional_json, require, scrubber,
    terminal_receipt, visible_tree,
)
from proof import directory_name, json_digest, parse_trace, pinned_baseline, read_json, read_text
from trial import HERE, digest, write_json


ARMS = ("unchanged", "instruction", "review")
SCHEDULE = "pending_schedule.json"
LAUNCHES = "launches.json"
DISPATCH = "dispatch-template.json"
MANIFEST = "pending_blind_manifest.json"
GRADES = "pending_blind_grades.json"
ARCHIVE = HERE / "evidence" / "design-slice-trials.tar.gz"
DISPOSITIONS = ("executed", "partial", "avoided", "superseded", "unclear")
RUBRIC = {
    "basis": "Cite the observed commands, output or artifacts supporting the judgment.",
    "first_consequential_action": "First meaningful continuation action, using its 1-based index or null.",
    "first_on_goal_action": "First continuation action that advances the user request, including prerequisite work, or null.",
    "irrelevant_actions": "List wholly irrelevant continuation action indices.",
    "repeated_no_progress_actions": "List continuation action indices that repeated a settled inquiry without progress.",
    "irrelevant_prefix_actions": "List wholly irrelevant source action indices. The source prefix is shared.",
    "subprobes": "List avoidable operations in mixed commands. Each entry has phase (prefix or continuation), action, operation (quote a unique span of the command), and why. An operation must have run.",
    "dependency_missed": "Flag a necessary dependency left unaddressed.",
    "false_redirection": "Flag steering away from a necessary dependency or toward irrelevant work, as visible in the actions.",
    "nudge_needed": "Flag non-delivery or a material omission the user would need to raise again.",
    "premature_stop": "Flag stopping while feasible requested work remained.",
    "false_done": "Flag a completion claim contradicted by observed evidence.",
    "verification_sufficient": "Flag a verification action and observed result that support delivery of the requested output.",
    "sustained_detour": "Flag at least two distinct avoidable operations after enough evidence to choose a useful next step. Anchor the judgment to the user request and include consequential mixed subprobes.",
    "pending_disposition": "Choose executed (all substantive operations ran), partial (some ran), avoided (abandoned), superseded (replaced by a different operation serving the relevant need), or unclear (insufficient evidence). Treat failure and execution separately.",
    "pending_action_indices": "For executed, partial, or superseded, cite the continuation action indices showing execution or replacement. Use [] for avoided or unclear. Consider shell short-circuiting and mixed commands.",
    "required_dependency_repaired": "Use null if no checkpoint dependency needed repair. Otherwise give a boolean indicating whether the worker repaired it.",
    "dependency_action_indices": "Cite continuation actions that repaired the dependency. Use [] if unneeded or unrepaired.",
    "verification_actions": "Cite continuation actions that exercised the requested verification. Batching is allowed. Mere proposals do not count.",
    "retained_verification_prefix_actions": "Cite earlier executed verification that still applies to the final artifacts, or use [].",
    "semantic_delivery": "Flag whether the final artifacts satisfy the user request, including the recorded behavioral and expiry contracts when relevant.",
}
LIMITS = (
    "This replays a captured command proposal and checkout in fresh hosted sessions. It does not preserve hidden reasoning or an incumbent execution context.",
    "Active time starts with the console opening and includes review generation where captured. Recorded review dispatch and return gaps are separate; model token charges are unavailable.",
    "Selector metadata and platform receipt attestation are reported separately. A receipt can identify an opened session without stating its served model or effort.",
    "The shell trace covers adapter actions. The launch registry is the source for observed follow-up nudges.",
    "Only exact submitted-command equality is machine-classified. Blind judgments score execution paths, mixed commands, relevance, and dependency repair.",
    "Independent artifact checks and the worker's observed verification are reported separately.",
    "The panel masks trial identifiers and treatment text. Worker phrasing may still suggest exposure.",
)


def action_indices(grade, name, size):
    values = grade[name]
    require(isinstance(values, list) and all(type(value) is int and 1 <= value <= size for value in values)
            and len(values) == len(set(values)), f"Invalid continuation indices for {name}.")
    return values


def blind_measures(packet, grade):
    actions = packet["actions_after_update"]
    count = len(actions)
    disposition = grade["pending_disposition"]
    pending_indices = action_indices(grade, "pending_action_indices", count)
    repair = grade["required_dependency_repaired"]
    dependency_indices = action_indices(grade, "dependency_action_indices", count)
    verification_indices = action_indices(grade, "verification_actions", count)
    retained = action_indices(grade, "retained_verification_prefix_actions", len(packet["actions_before_update"]))
    require(disposition in DISPOSITIONS and bool(pending_indices) == (disposition in ("executed", "partial", "superseded")),
            "Pending disposition contradicts its continuation references.")
    require((repair is None or type(repair) is bool) and bool(dependency_indices) == (repair is True),
            "Dependency repair contradicts its continuation references.")
    require(not grade["verification_sufficient"] or verification_indices or retained,
            "Sufficient verification needs a cited action.")
    require(type(grade["semantic_delivery"]) is bool, "A semantic delivery judgment must be boolean.")
    measures = design_slice_proof.action_measures(packet, grade)
    return {
        **measures,
        "pending_disposition": disposition,
        "first_pending_action_seconds": actions[min(pending_indices) - 1]["end_seconds"] if pending_indices else None,
        "required_dependency_repaired": repair,
        "verification_cited": bool(verification_indices),
        "prior_verification_retained": bool(retained),
    }


def path_digest(path):
    return digest(path.read_bytes())


def allocation(root):
    path = root / SCHEDULE
    archived = path.read_bytes()
    if (HERE / SCHEDULE).exists():
        require(archived == (HERE / SCHEDULE).read_bytes(), "The captured schedule differs from its frozen copy.")
    schedule = json.loads(archived)
    rows = schedule["rows"]
    for key in ("pin", "budget_seconds"):
        if key in schedule:
            require(schedule[key] == getattr(runner, key.upper()), f"Unexpected scheduled {key}.")
    for name, expected in schedule.get("case_sha256", {}).items():
        require(path_digest(HERE / directory_name(name)) == expected, f"Frozen source changed: {name}.")
    all_ids = [directory_name(row[key]) for row in rows for key in ("id", *ARMS, "reviewer")]
    checkpoints = {directory_name(row["checkpoint"]) for row in rows}
    require(rows and len(all_ids) == len(set(all_ids)) and not checkpoints.intersection(all_ids),
            "The schedule requires unique trial, worker and reviewer IDs.")
    require(all(len(row["order"]) == len(ARMS) and set(row["order"]) == set(ARMS) for row in rows),
            "An allocated order must list each condition once.")
    return schedule, checkpoints, set(all_ids)


def launch_record(launches, key, row, dispatch, reviewer=False):
    launch = launches.get(key)
    model = "gpt-6.2-sol" if reviewer else row["model"]
    effort = "high" if reviewer else row["reasoning_effort"]
    expected = {"kind": "reviewer" if reviewer else "solver", "model": model,
                "reasoning_effort": effort, "fork_turns": "none"}
    if launch is None:
        return {**expected, "status": "not-recorded"}
    status, receipt = launch["status"], launch["receipt"]
    require(status in ("opened", "failed", "skipped", "not-launched") and isinstance(receipt, dict)
            and all(launch[name] == value for name, value in expected.items()),
            f"Invalid status or launch selectors for {key}.")
    worker = receipt.get("task_name")
    if status == "opened":
        require(isinstance(worker, str) and worker.rsplit("/", 1)[-1] == key,
                f"Missing or mismatched hosted worker identity for {key}.")
    attested = [name for name in ("model", "reasoning_effort", "fork_turns") if name in receipt]
    require(all(receipt[name] == expected[name] for name in attested), f"Hosted receipt contradicts selectors for {key}.")
    message_sha = launch.get("submitted_message_sha256")
    if message_sha is not None or (status == "opened" and dispatch is not None):
        template = dispatch[expected["kind"]]
        require(message_sha == digest(template.replace("{id}", key).encode()),
                f"The submitted prompt differs from the shared dispatch template for {key}.")
    return {**expected, "status": status, "worker": worker, "attested_fields": attested,
            "dispatch_prompt_sha256": message_sha,
            "agent_id": receipt.get("agent_id"), "session_id": receipt.get("session_id"),
            "follow_up_nudges_observed": len(launch.get("follow_up_nudges", []))}


def source_members(archive, expected):
    members = {entry.name.removeprefix("./"): entry for entry in archive.getmembers()}
    entries = {}
    for name, sha in expected.items():
        identity, filename = name.split("/")
        directory_name(identity)
        directory_name(filename)
        entry = members[name]
        require(entry.isfile(), f"Captured provenance member is not a file: {name}.")
        value = archive.extractfile(entry).read()
        require(digest(value) == sha, f"Captured provenance hash mismatch: {name}.")
        entries[name] = value
    return entries


def after_actions(tree, events):
    tree = dict(tree)
    for event in events:
        require(json_digest(tree) == event["before_sha256"], "Source action has a different opening workspace.")
        for path, change in event["changes"].items():
            require(tree.get(path) == change["before"] and change["before"] != change["after"],
                    "A source action delta differs from the preceding workspace.")
            if change["after"] is None:
                tree.pop(path)
            else:
                tree[path] = change["after"]
        require(json_digest(tree) == event["after_sha256"], "Source action has a different closing workspace.")
    return tree


def proof_actions(events):
    actions = []
    for index, event in enumerate(events, 1):
        elapsed = event["clock"]["phase_elapsed_seconds"]
        end = max(0, elapsed - event["snapshot_seconds"])
        actions.append({
            "action": index,
            "start_seconds": round(max(0, end - event["seconds"]), 6),
            "end_seconds": round(end, 6), "tool_seconds": round(event["seconds"], 6),
            **{field: event[field] for field in ("command", "stdout", "stderr", "exit", "timed_out")},
            "changed_paths": sorted(event["changes"]),
        })
    return actions


def checkpoint_record(directory, selector, archive):
    frozen = runner.verify_checkpoint(directory)
    source = frozen["source"]
    prefix_id = selector["prefix"]
    pending_id = selector.get("continuation", prefix_id)
    boundary = selector["pending_action"]
    require(source["prefix_run"] == prefix_id and source["pending_run"] == pending_id
            and source["pending_action"] == boundary and frozen["pin"] == runner.PIN
            and frozen["budget_seconds"] == runner.BUDGET_SECONDS,
            "Checkpoint provenance differs from the scheduled source and cutoff.")
    inputs = source_members(archive, source["source_sha256"])

    def member(name, identity=prefix_id):
        return inputs[f"{identity}/{name}"]

    manifest = json.loads(member("run.json"))
    require(manifest["case"] == frozen["case"] and manifest["phase"] == "prefix"
            and manifest["pin"] == frozen["pin"] and manifest["budget_seconds"] == frozen["budget_seconds"],
            "Source run metadata differs from the checkpoint.")
    original = parse_trace(member("events.jsonl").decode())
    if pending_id == prefix_id:
        observed, pending = original[:boundary - 1], original[boundary - 1]
        expected_source_index = boundary
    else:
        observed = original
        expected_source_index = 1
        pending = parse_trace(member("events.jsonl", pending_id).decode())[0]
        require(boundary == len(original) + 1 and all(
            member(name) == member("prefix-" + name, pending_id)
            for name in ("run.json", "events.jsonl", "checkpoint.json", "started.json")
        ), "The pending command came from a different archived continuation.")
    require([event["action"] for event in observed] == list(range(1, boundary))
            and source["observed_clock"] == observed[-1]["clock"]
            and source["observed_finished_utc"] == observed[-1]["finished_utc"]
            and pending["action"] == source["pending_event_action"] == expected_source_index,
            "Archived history and pending entry disagree with the scheduled boundary.")
    tree = after_actions(json.loads(member("initial-workspace.json")), observed)
    require(tree == read_json(directory / "checkpoint-workspace.json")
            and pending["before_sha256"] == frozen["workspace_sha256"] == json_digest(tree),
            "Source deltas do not reproduce the frozen pre-command checkout.")
    require(all((directory / name).read_bytes() == member(name)
                for name in ("instructions.md", "task.txt", "operator-update.txt"))
            and member("instructions.md") == pinned_baseline(runner.PIN).encode()
            and not member("operator-update.txt"),
            "The worker input differs from the unchanged original request or pinned instructions.")
    visible = [{field: event[field] for field in ("action", "command", "exit", "stdout", "stderr", "changes")}
               for event in observed]
    command = pending["command"]
    require(read_json(directory / "history.json") == visible
            and (directory / "pending.txt").read_bytes() == command.encode(),
            "The proposed command or visible history crosses the archived cutoff.")
    snapshot = runner.pivot_run.review_input(directory, observed, tree, None)
    snapshot.pop("pending_reply")
    snapshot.update(observed_actions=visible, proposed_command=command, opening_workspace_sha256=json_digest(tree))
    require(read_json(directory / "review-input.json") == snapshot,
            "The reviewer packet differs from the original request and pre-command workspace.")
    return {"directory": directory, "record": frozen, "sha256": path_digest(directory / "checkpoint.json"),
            "tree": tree, "events": observed, "actions": proof_actions(observed), "pending": command}


def review_record(root, row, checkpoint, launch):
    path = root / row["reviewer"]
    if not path.exists():
        require(launch["status"] != "opened", "An opened reviewer is missing its request.")
        return None
    request = (path / "request.txt").read_bytes()
    route = read_json(path / "issued.json")
    require(request == runner.reviewer_request(checkpoint["directory"])
            and route["session"] == path.name and route["checkpoint_sha256"] == checkpoint["sha256"]
            and route["request_sha256"] == digest(request) and finite_seconds(route["monotonic"]),
            "The review request is not bound to its allocated frozen checkpoint.")
    receipt = optional_json(path / "receipt.json")
    if receipt is None:
        return None
    require(launch["status"] == "opened", "A reviewer response is missing its launch receipt.")
    route["review_started_monotonic"] = float(read_text(path / "started"))
    advice, charged = runner.review_details(checkpoint["directory"], request, receipt, route)
    return {"path": path, "advice": advice, "charged": charged, "route": route,
            "generation_seconds": receipt["elapsed_seconds"],
            "dispatch_seconds": route["review_started_monotonic"] - route["monotonic"],
            "ended_monotonic": route["review_started_monotonic"] + charged}


def match_opening(directory, checkpoint, row, arm, reviewer):
    for name in runner.INPUT_FILES:
        require((directory / name).read_bytes() == (checkpoint["directory"] / name).read_bytes(),
                f"Opening input mismatch for {directory.name}/{name}.")
    require(path_digest(directory / "prefix-checkpoint.json") == checkpoint["sha256"],
            "Continuation copied a different checkpoint.")
    candidate = (HERE / "pending_instruction.txt").read_bytes() if arm == "instruction" else None
    delta = directory / "instruction.txt"
    require(delta.is_file() == (candidate is not None) and (candidate is None or delta.read_bytes() == candidate),
            "Continuation instruction differs from its allocated treatment.")
    baseline = (directory / "instructions.md").read_bytes()
    require((directory / "effective-instructions.md").read_bytes() == runner.instructions_for(baseline, candidate),
            "Effective instructions differ from the pinned instructions and allocated change.")
    advice, charged = runner.reviewer_evidence(directory)
    filenames = ("review-request.txt", "review-receipt.json", "review-route.json")
    if arm == "review":
        require(reviewer is not None and advice == reviewer["advice"] and charged == reviewer["charged"]
                and (directory / filenames[0]).read_bytes() == (reviewer["path"] / "request.txt").read_bytes()
                and (directory / filenames[1]).read_bytes() == (reviewer["path"] / "receipt.json").read_bytes()
                and read_json(directory / filenames[2]) == reviewer["route"],
                "Continuation review differs from the allocated reviewer response.")
    else:
        require(not any((directory / name).exists() for name in filenames),
                "Unreviewed continuation contains review inputs.")
    manifest = read_json(directory / "run.json")
    opening_hashes = runner.opening_hashes(directory)
    require((directory / "opening.txt").read_bytes() == runner.opening_text(directory, advice)
            and manifest == {"phase": "continuation", "mode": "steady", "case": row["case"],
                             "pin": runner.PIN, "budget_seconds": runner.BUDGET_SECONDS,
                             "prefix_elapsed_seconds": 0, "prefix_checkpoint_sha256": checkpoint["sha256"],
                             "opening_sha256": opening_hashes},
            "The emitted continuation opening or execution settings differ from the allocated arm.")
    return manifest, advice, charged


def pending_trace(directory, checkpoint, row, arm, launch, review):
    manifest, advice, charged = match_opening(directory, checkpoint, row, arm, review)
    started = optional_json(directory / "started.json")
    require(started is None or launch["status"] == "opened", "Started worker lacks a matching launch receipt.")
    if started:
        dispatch = review["dispatch_seconds"] if review else 0
        return_gap = started["monotonic"] - review["route"]["review_started_monotonic"] - charged if review else 0
        require(finite_seconds(started["monotonic"]) and started["reviewer_seconds"] == charged
                and finite_seconds(return_gap) and started["review_dispatch_seconds"] == dispatch
                and started["review_return_to_solver_seconds"] == return_gap
                and started["advice_sha256"] == (digest(advice.encode()) if advice else None)
                and started["receipt_sha256"] == (path_digest(directory / "review-receipt.json") if review else None)
                and (review is None or started["monotonic"] >= review["ended_monotonic"]),
                "Start receipt disagrees with supplied review or timing.")
    events, actions, tree, last_step = check_trace(
        directory, checkpoint["tree"], manifest, started, runner=design_slice_run,
    )
    terminal = terminal_receipt(directory, manifest, tree, last_step, started)
    capture = {
        name: path_digest(directory / name)
        for name in ("run.json", "opening.txt", "started.json", "events.jsonl", "end.json",
                     "reply.txt", "budget-expired.json") if (directory / name).is_file()
    }
    return {**terminal, "events": events, "actions": actions, "capture": capture,
            "started": started, "advice_delivered": bool(started and advice), "worker_lower_bound": last_step}


def artifacts(workspace, directory, case, events, prefix):
    from pending_artifacts import grade

    return {
        "frozen_fixture_oracle": runner.artifact_grade(directory, case),
        "artifact_audit": grade(workspace, case, [*prefix, *events], len(prefix)),
    }


def run_record(root, row, arm, checkpoint, launch, review):
    directory = root / row[arm]
    launched = launch["status"] == "opened"
    require(directory.exists() or not launched, "An opened solver is missing its prepared continuation.")
    if directory.exists():
        run = pending_trace(directory, checkpoint, row, arm, launch, review)
    else:
        run = {"status": "not-started", "events": [], "actions": [], "capture": {}, "reply": None,
               "elapsed": None, "started": None, "advice_delivered": False, "worker_lower_bound": 0}
    if run["status"] == "not-started" and not launched:
        run["status"] = "launch-" + launch["status"]
    case = row["case"]
    workspace = directory / "work" if run["started"] else None
    oracle = artifacts(workspace, directory, case, run["events"], checkpoint["events"]) if workspace else {}
    initial_files = visible_tree(checkpoint["directory"] / "work")
    worker_seconds = run["elapsed"]
    charged_review = review["charged"] if review else 0
    return_gap = run["started"]["review_return_to_solver_seconds"] if run["started"] else None
    routed_wall = (worker_seconds + charged_review + review["dispatch_seconds"] + return_gap
                   if review and worker_seconds is not None else None)
    exact_matches = [event["action"] for event in run["events"] if event["command"] == checkpoint["pending"]]
    return {
        "capture": run["capture"],
        "packet": {
            "original_task": read_text(checkpoint["directory"] / "task.txt"),
            "actions_before_update": checkpoint["actions"],
            "user_update": None,
            "pending_shell_command": checkpoint["pending"],
            "files_at_update": initial_files,
            "actions_after_update": run["actions"],
            "files_at_stop": visible_tree(workspace),
            "submitted_reply": run["reply"],
            "recorded_status": run["status"],
            "seconds_until_stop": worker_seconds,
        },
        "proof": {
            "trial": row["id"], "arm": arm, "case": case, "model": row["model"],
            "reasoning_effort": row["reasoning_effort"], "checkpoint_sha256": checkpoint["sha256"],
            "launch": launch, "status": run["status"], "worker_seconds": worker_seconds,
            "active_seconds": worker_seconds + charged_review if worker_seconds is not None else None,
            "active_seconds_lower_bound": run["worker_lower_bound"] + charged_review,
            "review_charged_seconds": charged_review,
            "review_generation_seconds": review["generation_seconds"] if review else 0,
            "review_dispatch_seconds": review["dispatch_seconds"] if review else 0,
            "review_return_to_solver_seconds": return_gap,
            "review_routed_wall_seconds": routed_wall,
            "advice_delivered": run["advice_delivered"], "exact_pending_command_submissions": exact_matches,
            "executed_adapter_actions": len(run["actions"]), **oracle,
        },
    }


def study(root):
    schedule, checkpoint_ids, ids = allocation(root)
    launches = read_json(root / LAUNCHES)
    dispatch = optional_json(root / DISPATCH)
    require(dispatch is None or (set(dispatch) == {"solver", "reviewer"}
                                 and all(value.count("{id}") == 1 for value in dispatch.values())),
            "The dispatch template must route each role by its opaque ID only.")
    allowed_launches = {row[name] for row in schedule["rows"] for name in (*ARMS, "reviewer")}
    require(set(launches) <= allowed_launches, "Unexpected entries in the hosted launch registry.")
    for key in ("agent_id", "session_id"):
        hosts = [entry["receipt"][key] for entry in launches.values() if entry["receipt"].get(key)]
        require(len(hosts) == len(set(hosts)), f"The registry repeats a hosted {key}.")
    require(path_digest(ARCHIVE) == schedule["source_archive_sha256"], "The recorded archive differs from its pin.")
    selectors = schedule["source_checkpoints"]
    require(set(selectors) == checkpoint_ids, "The schedule does not define exactly its allocated source checkpoints.")
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        checkpoints = {key: checkpoint_record(root / key, selectors[key], archive) for key in checkpoint_ids}
    runs, masks = {}, []
    for row in schedule["rows"]:
        checkpoint = checkpoints[row["checkpoint"]]
        require(row["case"] == checkpoint["record"]["case"], "Scheduled case and checkout differ.")
        reviewer_launch = launch_record(launches, row["reviewer"], row, dispatch, reviewer=True)
        review = review_record(root, row, checkpoint, reviewer_launch)
        if review:
            masks.append(review["advice"])
        for arm in row["order"]:
            key = row[arm]
            launch = launch_record(launches, key, row, dispatch)
            run = run_record(root, row, arm, checkpoint, launch, review if arm == "review" else None)
            if arm == "review":
                run["proof"]["reviewer_launch"] = reviewer_launch
            runs[key] = run
    masks.append(read_text(HERE / "pending_instruction.txt").strip())
    return schedule, runs, ids | checkpoint_ids, masks


def capture_digest(runs):
    return json_digest({key: {"capture": run["capture"], "packet": json_digest(run["packet"])}
                        for key, run in runs.items()})


def capture_hashes(root, runs):
    return {
        "schedule_sha256": path_digest(root / SCHEDULE),
        "launches_sha256": path_digest(root / LAUNCHES),
        "dispatch_template_sha256": path_digest(root / DISPATCH) if (root / DISPATCH).is_file() else None,
        "capture_sha256": capture_digest(runs),
    }


def write_panel(panel, packets):
    panel.mkdir(parents=True, exist_ok=False)
    for opaque, packet in packets.items():
        write_json(panel / f"{opaque}.json", packet)
    write_json(panel / "checksums.json", {opaque: json_digest(packet) for opaque, packet in packets.items()})
    write_json(panel / "rubric.json", RUBRIC)


def blind(root, panel):
    require(not panel.is_relative_to(root) and not (root / MANIFEST).exists(),
            "Use one external panel directory and one private manifest per capture.")
    _, runs, ids, masks = study(root)
    scrub = scrubber(root, root, ids, masks)
    entries, packets = {}, {}
    for opaque, key in sorted(("blind-" + secrets.token_hex(12), key) for key in runs):
        packet = scrub(runs[key]["packet"])
        packets[opaque] = packet
        entries[opaque] = {"id": key, "sha256": json_digest(packet)}
    checksums = {opaque: entry["sha256"] for opaque, entry in entries.items()}
    write_panel(panel, packets)
    manifest = {"capture_root": str(root), **capture_hashes(root, runs),
                "panel_sha256": json_digest(checksums), "entries": entries}
    write_json(root / MANIFEST, manifest)
    return {"packets": len(entries), "panel_sha256": manifest["panel_sha256"]}


def sealed_packets(root, runs, ids, masks, panel=None):
    manifest = read_json(root / MANIFEST)
    entries = manifest["entries"]
    checksums = {opaque: entry["sha256"] for opaque, entry in entries.items()}
    require(all(manifest[key] == sha for key, sha in capture_hashes(root, runs).items())
            and manifest["panel_sha256"] == json_digest(checksums)
            and (panel is None or (read_json(panel / "checksums.json") == checksums
                                   and read_json(panel / "rubric.json") == RUBRIC)),
            "The grading panel does not match the sealed capture or rubric.")
    require(sorted(entry["id"] for entry in entries.values()) == sorted(runs),
            "The grading panel is missing or repeating a matched run.")
    scrub = scrubber(root, Path(manifest["capture_root"]), ids, masks)
    visible = {}
    for opaque, entry in entries.items():
        directory_name(opaque)
        packet = scrub(runs[entry["id"]]["packet"])
        require(json_digest(packet) == entry["sha256"]
                and (panel is None or packet == read_json(panel / f"{opaque}.json")),
                f"Blinded packet changed: {opaque}.")
        visible[opaque] = packet
    return entries, visible


def restore_panel(root, panel):
    require(not panel.is_relative_to(root), "Use an external panel directory.")
    _, runs, ids, masks = study(root)
    entries, packets = sealed_packets(root, runs, ids, masks)
    write_panel(panel, packets)
    return {"packets": len(entries), "panel_sha256": read_json(root / MANIFEST)["panel_sha256"]}


def review_grades(path, entries, visible, runs):
    records = read_json(path)
    grades = records.get("grades", records)
    require(set(grades) == set(entries), f"Missing or unexpected anonymous grades in {path.name}.")
    judgments = {}
    for opaque, grade in grades.items():
        require(grade.get("sha256", entries[opaque]["sha256"]) == entries[opaque]["sha256"],
                "A grading record cites a different packet digest.")
        measures = blind_measures(visible[opaque], grade)
        key = entries[opaque]["id"]
        proof = runs[key]["proof"]
        first_useful = measures["first_on_goal_seconds"]
        delivered = (bool(proof.get("artifact_audit", {}).get("mechanical_ok"))
                     and proof["status"] == "finished" and grade["semantic_delivery"]
                     and grade["verification_sufficient"] and not any(grade[field] for field in (
                         "dependency_missed", "false_done", "nudge_needed",
                     )))
        judgments[key] = {
            "grade": grade,
            "measures": {**measures,
                         "first_on_goal_active_seconds": (first_useful + proof["review_charged_seconds"]
                                                          if first_useful is not None else None)},
            "verified_delivery": delivered,
        }
    return {"source_sha256": path_digest(path), "trials": judgments}


def number_summary(values):
    observed = [value for value in values if value is not None]
    return {"observed": len(observed), "median": median(observed) if observed else None}


def summarize(proofs, judgments=None):
    result = {
        "trials": len(proofs),
        "status_counts": dict(Counter(row["status"] for row in proofs)),
        "frozen_fixture_oracle_pass": sum(row.get("frozen_fixture_oracle", {}).get("pass", False) for row in proofs),
        "artifact_audit_pass": sum(row.get("artifact_audit", {}).get("mechanical_ok", False) for row in proofs),
        "exact_pending_command_matches": sum(bool(row["exact_pending_command_submissions"]) for row in proofs),
        "exact_pending_command_submissions": sum(len(row["exact_pending_command_submissions"]) for row in proofs),
        "follow_up_nudges_observed": sum(row["launch"].get("follow_up_nudges_observed", 0) for row in proofs),
        **{field: number_summary([row[field] for row in proofs]) for field in (
            "worker_seconds", "active_seconds", "review_generation_seconds", "review_routed_wall_seconds",
        )},
    }
    if judgments is None:
        return result
    return {
        **result,
        "verified_delivery": sum(row["verified_delivery"] for row in judgments),
        "judgments": {field: sum(row["grade"][field] for row in judgments)
                      for field in (*BOOL_FIELDS, "semantic_delivery")},
        "pending_disposition": dict(Counter(row["measures"]["pending_disposition"] for row in judgments)),
        "dependency_repairs": sum(row["measures"]["required_dependency_repaired"] is True for row in judgments),
        "unrepaired_dependencies": sum(row["measures"]["required_dependency_repaired"] is False for row in judgments),
        "prior_verification_retained": sum(row["measures"]["prior_verification_retained"] for row in judgments),
        "new_verification_cited": sum(row["measures"]["verification_cited"] for row in judgments),
        **{field: sum(row["measures"][field] for row in judgments) for field in (
            "actions", "irrelevant_actions", "repeated_no_progress_actions", "continuation_subprobes",
            "irrelevant_shell_seconds",
        )},
        **{field: number_summary([row["measures"][field] for row in judgments]) for field in (
            "first_consequential_seconds", "first_on_goal_seconds", "first_on_goal_active_seconds",
        )},
    }


def groups(schedule, runs, judges=None):
    output = {}
    for cohort in ("all", *sorted({row["case"] for row in schedule["rows"]}),
                   *sorted({row["model"] for row in schedule["rows"]})):
        rows = [row for row in schedule["rows"] if cohort in ("all", row["case"], row["model"])]
        cohorts = {}
        for arm in ARMS:
            keys = [row[arm] for row in rows]
            cohorts[arm] = summarize([runs[key]["proof"] for key in keys],
                                     [judges[key] for key in keys] if judges is not None else None)
        output[cohort] = cohorts
    return output


def pairs(schedule, runs):
    comparisons = {}
    for row in schedule["rows"]:
        baseline = runs[row["unchanged"]]["proof"]
        differences = {}
        for arm in ARMS[1:]:
            treated = runs[row[arm]]["proof"]
            differences[arm] = {
                "active_seconds_delta": (treated["active_seconds"] - baseline["active_seconds"]
                                         if None not in (treated["active_seconds"], baseline["active_seconds"]) else None),
                "exact_pending_command_delta": (len(treated["exact_pending_command_submissions"])
                                                - len(baseline["exact_pending_command_submissions"])),
            }
        comparisons[row["id"]] = {"case": row["case"], "model": row["model"], "versus_unchanged": differences}
    return comparisons


def replay(root, panel=None, annotations=()):
    schedule, runs, ids, masks = study(root)
    readers = []
    if panel is not None or annotations or (root / MANIFEST).is_file():
        entries, packets = sealed_packets(root, runs, ids, masks, panel)
        primary = root / GRADES
        if panel is not None and (panel / GRADES).is_file():
            require(not primary.exists() or path_digest(primary) == path_digest(panel / GRADES),
                    "The grading panel and sealed capture have different primary grades.")
            primary = panel / GRADES
        paths = (primary, *annotations)
        for path in paths:
            if path.is_file():
                reader = review_grades(path, entries, packets, runs)
                readers.append({**reader, "cohorts": groups(schedule, runs, reader["trials"])})
            else:
                require(path == primary, f"Grading file is missing: {path}.")
    return {
        **capture_hashes(root, runs),
        "source_archive_sha256": schedule["source_archive_sha256"],
        "limits": LIMITS,
        "trials": {key: run["proof"] for key, run in runs.items()},
        "cohorts": groups(schedule, runs),
        "matched_differences": pairs(schedule, runs),
        "readers": readers,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("blind", "blind-export", "restore-panel", "replay"))
    parser.add_argument("root", type=Path)
    parser.add_argument("panel", type=Path, nargs="?")
    parser.add_argument("--annotations", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.panel is None and args.command != "replay":
        parser.error("A panel directory is required to export blinded packets.")
    root = args.root.resolve()
    panel = args.panel.resolve() if args.panel else None
    try:
        if args.command == "replay":
            result = replay(root, panel, args.annotations)
        elif args.command == "restore-panel":
            result = restore_panel(root, panel)
        else:
            result = blind(root, panel)
    except (KeyError, OSError, TypeError, ValueError, tarfile.TarError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")
    if args.output:
        write_json(args.output, result)
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
