"""Export blinded priority-pivot traces and replay their delivery and timing evidence."""

import argparse
import json
import math
import re
import secrets
import subprocess
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

import pivot_run
from long_run import workspace_tree
from proof import directory_name, json_digest, parse_trace, pinned_baseline, read_json, read_text
from trial import HERE, digest, write_json


SCHEDULE = "pivot_schedule.json"
SCHEDULE_SHA256 = "826cd0541bab13ba20a2761a4c1b6a35c7de58762b23b17ab2e778e373bb9675"
STEADY = "pivot_steady_schedule.json"
RUNNER_SHA256 = "ed7fb254ab0e8d18b70daff1a33cb6777bffe055c1dd6a9394b77e50b2829441"
STEADY_SHA256 = "009ac541f333588d658162970e8488fe5efc455f68726ccb771365505dedff06"
MANIFEST = "pivot_blind_manifest.json"
GRADES = "pivot_blind_grades.json"
LAUNCHES = "launches.json"
ARMS = ("baseline", "candidate")
FIRST_FIELDS = ("first_consequential_action", "first_on_goal_action")
ACTION_LISTS = ("irrelevant_actions", "repeated_no_progress_actions", "irrelevant_prefix_actions")
BOOL_FIELDS = ("dependency_missed", "false_redirection", "nudge_needed", "premature_stop", "false_done",
               "verification_sufficient", "sustained_detour")
REVIEW_ATTRIBUTION = re.compile(
    r"\b(?:reviewer|review agent|review advice|independent review|second reader)\b", re.IGNORECASE
)
LIMITS = (
    "The captured shell trace covers adapter calls. Hosted receipt fields attest model and effort only when present.",
    "The operator update arrives at the frozen action boundary. Its observation is separate from any follow-up intervention.",
    "Observed nudges come from recorded dispatch metadata. An empty log cannot establish absence on other channels.",
    "The oracle checks delivery and preservation. The blind grader labels relevance, verification and need for a nudge.",
    "False redirection judgments concern visible worker actions. They cannot establish whether unshown advice was sound.",
    "Irrelevant action duration is subprocess wall time for the entire tagged action, including batched work.",
    "Arm identifiers and advice are masked. Judge timestamps exclude review and routing. Worker text may still hint at exposure or case identity.",
    "The opening dialogue and local artifacts reconstruct observed workflow patterns. They are not a captured field detour.",
    "Fixture traffic and local effects cannot prove performance on a deployed workflow.",
)


def require(condition, explanation):
    if not condition:
        raise ValueError(explanation)


def frozen_json(root, name, expected):
    path = HERE / name
    require(digest(path.read_bytes()) == expected, f"The frozen input changed: {name}.")
    archived = root / name
    require(not archived.exists() or archived.read_bytes() == path.read_bytes(), f"Archive mismatch: {name}.")
    return read_json(path)


def schedule_for(root):
    schedule = frozen_json(root, SCHEDULE, SCHEDULE_SHA256)
    steady = frozen_json(root, STEADY, STEADY_SHA256)
    hashes = {**schedule["case_sha256"], "pivot_steady.py": steady["steady_history_sha256"],
              "pivot_run.py": RUNNER_SHA256}
    for name, expected in hashes.items():
        require(digest((HERE / name).read_bytes()) == expected, f"The frozen input changed: {name}.")
    rows = [{"mode": "operator-update", **row} for row in (*schedule["rows"], *steady["rows"])]
    ids = [directory_name(row[key]) for row in rows for key in ("id", *ARMS, "reviewer")]
    require(len(ids) == len(set(ids)), "The frozen allocation shares directory IDs.")
    require(schedule["pin"] == pivot_run.PIN and schedule["budget_seconds"] == pivot_run.BUDGET_SECONDS,
            "The runner differs from the frozen baseline or budget.")
    return {**schedule, "rows": rows}


def optional_json(path):
    return read_json(path) if path.exists() else None


def optional_hash(path):
    return digest(path.read_bytes()) if path.exists() else None


def finite_seconds(seconds):
    return type(seconds) in (int, float) and math.isfinite(seconds) and seconds >= 0


def checked_clock(clock, prefix, reviewer, budget, phase):
    step = clock["phase_elapsed_seconds"]
    require(finite_seconds(step) and clock["reviewer_seconds"] == reviewer
            and abs(clock["worker_elapsed_seconds"] - prefix - step) < 1e-6
            and abs(clock["total_elapsed_seconds"] - prefix - reviewer - step) < 1e-6
            and clock["prefix_elapsed_seconds"] == (step if phase == "prefix" else prefix)
            and clock["within_budget"] == (clock["total_elapsed_seconds"] <= budget),
            "The budget or clock arithmetic disagrees with the phase receipt.")
    return step


def utc_seconds(before, after):
    elapsed = (datetime.fromisoformat(after) - datetime.fromisoformat(before)).total_seconds()
    require(elapsed >= 0, "The captured UTC timestamps are out of order.")
    return elapsed


def check_trace(directory, entry, manifest, started):
    events = parse_trace(read_text(directory / "events.jsonl"))
    require(started is not None or not events, "Actions were captured before the console opened.")
    reviewer = started["reviewer_seconds"] if started else 0
    prefix = manifest.get("prefix_elapsed_seconds", 0)
    phase = manifest["phase"]
    tree, last, actions = dict(entry), 0, []
    for index, event in enumerate(events, 1):
        step = checked_clock(event["clock"], prefix, reviewer, manifest["budget_seconds"], phase)
        runtime, snapshot = event["seconds"], event["snapshot_seconds"]
        require(finite_seconds(runtime) and finite_seconds(snapshot), "The action duration is invalid.")
        ended, began = step - snapshot, step - snapshot - runtime
        require(event["action"] == index and event["phase"] == phase and last - 1e-6 <= began <= ended <= step
                and event["before_sha256"] == json_digest(tree)
                and event["artifact_changes"] == sorted(set(event["changes"]) & set(pivot_run.artifact_paths(manifest["case"]))),
                "A recorded action disagrees with its phase, state, or timing.")
        utc_seconds(started["utc"], event["started_utc"])
        utc_seconds(event["started_utc"], event["finished_utc"])
        for path, change in event["changes"].items():
            require(tree.get(path) == change["before"] and change["after"] != change["before"],
                    "A recorded file change disagrees with the previous state.")
            if change["after"] is None:
                tree.pop(path)
            else:
                tree[path] = change["after"]
        require(event["after_sha256"] == json_digest(tree), "The action delta does not reproduce its end state.")
        actions.append({"action": index, "start_seconds": round(max(0, began), 6),
                        "end_seconds": round(ended, 6), "tool_seconds": round(runtime, 6),
                        **{field: event[field] for field in ("command", "stdout", "stderr", "exit", "timed_out")},
                        "changed_paths": [path for path in event["changes"] if ".git" not in Path(path).parts]})
        last = step
    require(tree == workspace_tree(directory / "work"), "The archived checkout differs from the action trace.")
    return events, actions, tree, last


def opening_inputs(directory, manifest, row, schedule, baseline):
    case, mode = row["case"], row["mode"]
    require(manifest == {"case": case, "phase": "prefix", "mode": mode, "pin": schedule["pin"],
                        "budget_seconds": schedule["budget_seconds"],
                        "input_sha256": pivot_run.hash_files(directory, pivot_run.INPUT_FILES)},
            "The prefix manifest differs from the frozen inputs.")
    module = pivot_run.module(case)
    if mode == "steady":
        from pivot_steady import history

        original, update = history(case), ""
    else:
        original, update = module.history(case).split(pivot_run.UPDATE)
    require(read_text(directory / "instructions.md") == baseline
            and read_text(directory / "task.txt") == original.rstrip() + "\n"
            and read_text(directory / "operator-update.txt") == update,
            "The original task or user update differs from the frozen fixture.")
    opening = read_json(directory / "initial-workspace.json")
    with tempfile.TemporaryDirectory(prefix="codex-pivot-opening-") as scratch:
        workspace = Path(scratch) / "work"
        workspace.mkdir()
        module.prepare(workspace, case)
        rebuilt = workspace_tree(workspace)
    def comparable(tree):
        return {name: attrs for name, attrs in tree.items() if name != ".git/index"}

    require(comparable(opening) == comparable(rebuilt), "The opening fixture data does not reproduce.")
    return opening


def terminal_receipt(directory, manifest, trace, last, started):
    end = optional_json(directory / "end.json")
    expiry = optional_json(directory / "budget-expired.json")
    reply = directory / "reply.txt"
    prefix = manifest.get("prefix_elapsed_seconds", 0)
    reviewer = started["reviewer_seconds"] if started else 0
    status, elapsed = "unfinished" if started else "not-started", None
    if end:
        last_clock = end["clock"]
        elapsed = checked_clock(last_clock, prefix, reviewer, manifest["budget_seconds"], manifest["phase"])
        require(started is not None and elapsed >= last
                and end["trace_sha256"] == digest((directory / "events.jsonl").read_bytes())
                and end["workspace_sha256"] == json_digest(trace)
                and read_json(directory / "end-workspace.json") == trace
                and read_json(directory / "clock.json") == last_clock
                and end["prefix_checkpoint_sha256"] == manifest.get("prefix_checkpoint_sha256")
                and end["reason"] in ("reply", "budget-expired")
                and reply.is_file() == (end["reason"] == "reply") and end["reply_sha256"] == optional_hash(reply),
                "The terminal receipt disagrees with the captured actions, reply, or checkout.")
        utc_seconds(started["utc"], end["finished_utc"])
        status = "finished" if end["reason"] == "reply" and last_clock["within_budget"] else "budget-expired"
    else:
        require(not reply.exists(), "A submitted reply has no terminal receipt.")
    if expiry:
        expiry_phase = checked_clock(expiry, prefix, reviewer, manifest["budget_seconds"], manifest["phase"])
        require(expiry["total_elapsed_seconds"] >= manifest["budget_seconds"], "The expiry is under budget.")
        if end is None:
            elapsed = expiry_phase
            status = "budget-expired"
    return {"status": status, "elapsed": elapsed, "reply": read_text(reply) if reply.exists() else None, "end": end}


def prefix_record(directory, row, schedule, baseline):
    manifest = read_json(directory / "run.json")
    initial = opening_inputs(directory, manifest, row, schedule, baseline)
    started = optional_json(directory / "started.json")
    require(started is None or (started["reviewer_seconds"] == 0 and finite_seconds(started["monotonic"])),
            "A prefix has review time or an invalid start time.")
    events, actions, tree, last = check_trace(directory, initial, manifest, started)
    checkpoint = optional_json(directory / "checkpoint.json")
    pending = None
    if checkpoint:
        clock = checkpoint["clock"]
        step = checked_clock(clock, 0, 0, manifest["budget_seconds"], "prefix")
        path = directory / "review-input.json"
        pending = read_json(path)["pending_reply"]
        trigger = pivot_run.review_trigger(directory, manifest, events, tree)
        fixed = schedule["prefix_work_actions"]
        reason_rules = {
            "attempted-finish": row["mode"] == "operator-update" and pending is not None and len(events) < fixed,
            "two-shell-actions": row["mode"] == "operator-update" and pending is None and len(events) == fixed,
            "independent-inquiry-trigger": row["mode"] == "steady" and trigger["eligible"] and 2 <= len(events) <= 6,
            "six-shell-action-fallback": row["mode"] == "steady" and not trigger["eligible"] and len(events) == 6,
        }
        require(started is not None and step >= last and checkpoint["action_count"] == len(events)
                and reason_rules[checkpoint["reason"]] and checkpoint["review_trigger"] == trigger
                and checkpoint["workspace_sha256"] == json_digest(tree)
                and checkpoint["trace_sha256"] == digest((directory / "events.jsonl").read_bytes())
                and checkpoint["review_input_sha256"] == digest(path.read_bytes())
                and read_json(directory / "checkpoint-workspace.json") == tree
                and read_json(path) == pivot_run.review_input(directory, events, tree, pending),
                "The prefix checkpoint, review trigger, or reviewer source inputs do not reproduce.")
    end = terminal_receipt(directory, manifest, tree, last, started)
    require(not checkpoint or end["end"] is None, "A prefix has both an update boundary and a terminal reply.")
    return {"manifest": manifest, "checkpoint": checkpoint, "pending": pending, "actions": actions, "tree": tree,
            "started": started, "directory": directory, **end}


def branch_record(directory, prefix, review=None):
    source, checkpoint = prefix["directory"], prefix["checkpoint"]
    manifest = read_json(directory / "run.json")
    prefix_amount = checkpoint["clock"]["prefix_elapsed_seconds"]
    exact_files = (*pivot_run.INPUT_FILES, "checkpoint-workspace.json", "review-input.json")
    copied = {name: name for name in exact_files}
    copied.update({f"prefix-{name}": name for name in ("run.json", "checkpoint.json", "started.json", "events.jsonl")})
    for name, source_name in copied.items():
        require((directory / name).read_bytes() == (source / source_name).read_bytes(),
                f"A branch differs from the frozen prefix: {name}.")
    require(manifest == {**prefix["manifest"], "phase": "continuation", "prefix_elapsed_seconds": prefix_amount,
                         "prefix_checkpoint_sha256": optional_hash(source / "checkpoint.json")},
            "The branch manifest points to a different checkpoint.")
    started = optional_json(directory / "started.json")
    receipt = optional_json(directory / "review.json")
    advice_file = directory / "advice.txt"
    advice = read_text(advice_file) if advice_file.exists() else ""
    if receipt is not None or advice_file.exists():
        require(check_review_copy(receipt, review, advice),
                "The branch review files disagree with the eligible reviewer receipts.")
    captured_review_seconds = receipt["elapsed_seconds"] if receipt else 0
    if started:
        require(finite_seconds(started["monotonic"]) and started["reviewer_seconds"] == captured_review_seconds
                and (receipt is None or started["monotonic"] >= review["ended_monotonic"])
                and started["receipt_sha256"] == optional_hash(directory / "review.json")
                and started["advice_sha256"] == optional_hash(advice_file),
                "The consumed review files disagree with the branch start receipt.")
    events, actions, tree, last = check_trace(directory, prefix["tree"], manifest, started)
    terminal = terminal_receipt(directory, manifest, tree, last, started)
    return {**terminal, "actions": actions, "started": started, "tree": tree,
            "reviewer_seconds": captured_review_seconds, "advice_delivered": bool(started and advice.strip()),
            "directory": directory, "lower_bound": last}


def launch_entry(launch, key, kind, row, prefix=None):
    receipt = launch["receipt"]
    status = launch["status"]
    model = "gpt-6.2-sol" if kind == "reviewer" else row["model"]
    effort = "high" if kind == "reviewer" else row["reasoning_effort"]
    fork = {"prefix": "none", "reviewer": "none", "fork": "all"}.get(kind)
    require(launch["kind"] == kind and launch["model"] == model and launch["reasoning_effort"] == effort
            and status in ("opened", "failed", "skipped", "not-launched") and isinstance(receipt, dict) and receipt
            and (fork is None or launch["fork_turns"] == fork)
            and launch.get("parent") == prefix
            and all(launch[field] == receipt[field] for field in ("model", "reasoning_effort", "fork_turns")
                    if field in receipt),
            f"The launch selectors, scope, or receipt disagree for {key}.")
    worker = receipt.get("task_name")
    expected = prefix if kind == "incumbent" else key
    if status == "opened" and kind != "fork":
        require(isinstance(worker, str) and worker.rsplit("/", 1)[-1] == expected,
                f"The worker receipt does not identify the scheduled session: {key}.")
    if status == "opened" and kind == "fork":
        require(isinstance(worker, str) and worker.rsplit("/", 1)[0].rsplit("/", 1)[-1] == prefix,
                f"The fork receipt is outside the inherited worker history for {key}.")
    if kind == "incumbent" and status == "opened":
        move = launch["resume_receipt"]
        require(move["tool"] == "followup_task" and move["target"] == worker
                and "raw_tool_result" in move,
                f"The incumbent has no matching continuation dispatch for {key}.")
    return {
        "kind": kind, "status": status, "worker": worker,
        "model_attested_by_receipt": "model" in receipt,
        "effort_attested_by_receipt": "reasoning_effort" in receipt,
        "follow_up_nudges_observed": len(launch.get("follow_up_nudges", [])),
        "raw_resume_receipt_present": bool(launch.get("resume_receipt", {}).get("raw_tool_result")),
        "agent_id": receipt.get("agent_id"), "session_id": receipt.get("session_id"),
    }


def review_record(directory, prefix, launch):
    path = directory / "request.txt"
    reply = directory / "receipt.json"
    opened = launch["status"] == "opened"
    require(path.exists() or not opened, "An opened reviewer has no issued request.")
    if not path.exists():
        require(not reply.exists(), "A reviewer replied without a preserved request.")
        return None
    raw = path.read_bytes()
    role = (HERE / "pivot_reviewer.txt").read_bytes()
    snapshot = (prefix["directory"] / "review-input.json").read_bytes()
    require(raw == role + b"\n" + snapshot,
            "The reviewer received more than the frozen role and the captured checkpoint.")
    receipt = optional_json(reply)
    require(opened or receipt is None, "A failed reviewer launched a recorded response.")
    if receipt is None:
        return None
    require(receipt["session"] == directory.name and receipt["request_sha256"] == digest(raw)
            and finite_seconds(receipt["elapsed_seconds"]) and isinstance(receipt["advice"], str),
            "The reviewer advice or latency is not tied to the issued packet.")
    started = float(read_text(directory / "started"))
    boundary = prefix["started"]["monotonic"] + prefix["checkpoint"]["clock"]["prefix_elapsed_seconds"]
    require(finite_seconds(started) and started >= boundary, "The reviewer started before the eligible boundary.")
    advice = receipt["advice"].strip()
    if advice.casefold() in ("pass", "pass."):
        advice = ""
    stored = directory / "advice.txt"
    require(not stored.exists() or read_text(stored).strip() == advice, "The stored advice differs from the reviewer's reply.")
    return {"record": {**receipt, "request_sha256": digest(snapshot)}, "advice": advice, "original_receipt": receipt, "ended_monotonic": started + receipt["elapsed_seconds"]}


def check_review_copy(receipt, review, advice):
    return (review is not None and receipt is not None
            and receipt["elapsed_seconds"] == review["record"]["elapsed_seconds"]
            and receipt["request_sha256"] == review["record"]["request_sha256"]
            and receipt["reviewer_prompt_sha256"] == review["original_receipt"]["request_sha256"]
            and all(receipt[field] == review["record"][field] for field in ("session", "advice") if field in receipt)
            and advice.strip() == review["advice"].strip())


def branch_publication(row, arm, prefix, result, launch, review_launch, review, connected_dirs):
    checkpoint = prefix["checkpoint"]
    prefix_seconds = checkpoint["clock"]["prefix_elapsed_seconds"] if checkpoint else 0
    reviewer_seconds = result["reviewer_seconds"]
    update_observed = row["mode"] == "operator-update" and result["started"] is not None
    elapsed = result["elapsed"]
    charged = prefix_seconds + reviewer_seconds + elapsed if elapsed is not None else None
    seconds_at_boundary = elapsed + reviewer_seconds if elapsed is not None and checkpoint else None
    status = result["status"] if launch["status"] == "opened" else "launch-" + launch["status"]
    directory = result["directory"]
    workspace = directory / "work" if directory is not None else None
    available = result["started"] is not None
    oracle = pivot_run.artifact_grade(directory, row["case"]) if available else {}
    route, total_wall = None, None
    if checkpoint and available:
        offset = prefix_seconds + reviewer_seconds
        separation = result["started"]["monotonic"] - prefix["started"]["monotonic"]
        require(separation >= prefix_seconds, "Continuation opened before the shared checkpoint.")
        route = round(max(0, separation - offset), 6)
        total_wall = round(separation - prefix_seconds + elapsed, 6) if elapsed is not None else None
    reviewer_answered = review is not None
    packet_actions = [*prefix["actions"], *(result["actions"] if checkpoint else [])]
    text_observed = "\n".join([result["reply"] or "", *(action[field] for action in packet_actions
                                                           for field in ("command", "stdout", "stderr"))])
    explicit_attribution = bool(REVIEW_ATTRIBUTION.search(text_observed))
    advice_echoed = bool(review and review["advice"] and review["advice"] in text_observed)
    return {
        "original_task": read_text(prefix["directory"] / "task.txt"),
        "update": read_text(prefix["directory"] / "operator-update.txt"),
        "prefix_actions": prefix["actions"], "pending": prefix["pending"],
        "boundary_observed": checkpoint is not None, "update_observed": update_observed,
        "files_at_update": visible_tree(prefix["directory"] / "work") if checkpoint else None,
        "actions": result["actions"] if checkpoint else [],
        "end_files": visible_tree(workspace) if available else None,
        "reply": result["reply"], "status": status, "elapsed": elapsed if checkpoint else None,
        "directories": connected_dirs,
        "explicit_review_attribution": explicit_attribution,
        "verbatim_review_advice_echo": advice_echoed,
        "timing": {"reviewer_seconds": reviewer_seconds, "seconds_after_update": seconds_at_boundary,
                   "charged_seconds": charged, "worker_seconds_after_boundary": elapsed if checkpoint else None,
                   "prefix_seconds": prefix_seconds if checkpoint else elapsed,
                   "routing_seconds_excluded_from_budget": route,
                   "wall_seconds_after_boundary": total_wall,
                   "charged_seconds_lower_bound": round(prefix_seconds + reviewer_seconds + result["lower_bound"], 6)},
        "publication": {
            "prefix": row["id"], "case": row["case"], "mode": row["mode"], "model": row["model"],
            "reasoning_effort": row["reasoning_effort"], "arm": arm, "incumbent_arm": row["incumbent_arm"],
            "matched_checkpoint_sha256": optional_hash(prefix["directory"] / "checkpoint.json"),
            "checkpoint_reason": checkpoint["reason"] if checkpoint else None,
            "review_trigger": checkpoint["review_trigger"] if checkpoint else None,
            "eligible": bool(checkpoint and checkpoint["review_trigger"]["eligible"]),
            "reviewer_attempted": review_launch is not None,
            "reviewer_answered": reviewer_answered,
            "reviewer_recorded_seconds": review["original_receipt"]["elapsed_seconds"] if reviewer_answered else None,
            "advice_delivered": result["advice_delivered"], "launch": launch,
            "review_launch": review_launch,
            "budget_exceeded": (charged is not None and charged > prefix["manifest"]["budget_seconds"])
            or status == "budget-expired",
            "oracle": oracle, "follow_up_nudges_observed": launch.get("follow_up_nudges_observed", 0),
        },
    }


def missing_branch(directory):
    require(not any((directory / name).exists() for name in ("started.json", "end.json", "reply.txt")),
            "A missing launch has worker evidence.")
    return {"directory": None, "status": "not-started", "started": None, "actions": [], "elapsed": None,
            "reply": None, "reviewer_seconds": 0, "advice_delivered": False, "lower_bound": 0}


def study(root):
    schedule = schedule_for(root)
    launches = read_json(root / LAUNCHES)
    baseline = pinned_baseline(schedule["pin"])
    masks = [baseline.strip(), read_text(HERE / "pivot_reviewer.txt").strip()]
    runs, used = {}, set()
    worker_ids = defaultdict(set)

    def registered(key, kind, row, parent=None):
        if key not in launches:
            require(kind in ("reviewer", "fork", "incumbent"), f"A frozen prefix has no launch record: {key}.")
            return None
        used.add(key)
        entry = launch_entry(launches[key], key, kind, row, parent)
        if kind != "incumbent" and entry["status"] == "opened":
            masks.extend(str(entry[field]) for field in ("agent_id", "session_id", "worker") if entry[field])
            for field in ("agent_id", "session_id", "worker"):
                value = entry[field]
                if value is not None:
                    require(value not in worker_ids[field], "Two distinct sessions reused the same launch receipt.")
                    worker_ids[field].add(value)
        return entry

    for row in schedule["rows"]:
        prefix_id = row["id"]
        source = root / prefix_id
        source_launch = registered(prefix_id, "prefix", row)
        prefix = prefix_record(source, row, schedule, baseline)
        require(source_launch["status"] == "opened" or prefix["started"] is None,
                f"An unlaunched prefix has actions: {prefix_id}.")
        pivot = prefix["checkpoint"]
        if pivot is None:
            require(not any(row[key] in launches for key in (*ARMS, "reviewer")),
                    "A downstream session opened without a frozen boundary.")
            available = {**prefix, "advice_delivered": False, "reviewer_seconds": 0,
                         "lower_bound": prefix["actions"][-1]["end_seconds"] if prefix["actions"] else 0}
            runs[row["baseline"]] = branch_publication(row, "baseline", prefix, available, source_launch, None, None,
                                                       [source])
            continue
        review_key = row["reviewer"]
        review_launch = registered(review_key, "reviewer", row, prefix_id)
        review_dir = root / review_key
        require(pivot["review_trigger"]["eligible"] or (review_launch is None and not review_dir.exists()),
                "A reviewer attempted an ineligible checkpoint.")
        review = review_record(review_dir, prefix, review_launch) if review_launch is not None else None
        if review:
            masks.append(review["advice"])
        for arm in ARMS:
            key = row[arm]
            directory = root / key
            kind = "incumbent" if row["incumbent_arm"] == arm else "fork"
            launch = registered(key, kind, row, prefix_id)
            if launch is None:
                launch = {"kind": kind, "status": "not-launched", "worker": None}
            elif launch["status"] == "opened":
                worker, original_worker = launch["worker"], source_launch["worker"]
                require(worker == original_worker if kind == "incumbent" else worker.rsplit("/", 1)[0] == original_worker,
                        "A continuation receipt points to a different worker history.")
                if kind == "incumbent":
                    require(all(launch[field] is None or source_launch[field] is None
                                or launch[field] == source_launch[field] for field in ("agent_id", "session_id")),
                            "The incumbent continuation changed agent or session identity.")
            allowed = review if arm == "candidate" else None
            branch = (branch_record(directory, prefix, allowed) if (directory / "run.json").exists()
                      else missing_branch(directory))
            require(launch["status"] == "opened" or branch["started"] is None,
                    "A branch started without its launch receipt.")
            require(not (allowed and branch["started"]) or (directory / "review.json").exists(),
                    "A started candidate did not consume a completed reviewer receipt.")
            require(not branch["started"] or not branch["advice_delivered"] or arm == "candidate",
                    "The baseline was exposed to advice.")
            linked = [path for path in (source, directory, review_dir) if path.exists()]
            runs[key] = branch_publication(row, arm, prefix, branch, launch,
                                           review_launch if arm == "candidate" else None, allowed, linked)
    require(set(launches) == used, "The launch registry includes an unscheduled worker or exposure.")
    return schedule, runs, masks


def capture_digest(runs):
    directories = {path for run in runs.values() for path in run["directories"]}
    return json_digest({path.name: workspace_tree(path) for path in sorted(directories)})


def scrubber(root, original_root, ids, secrets_to_mask):
    replacements = {value: "<masked>" for value in secrets_to_mask if value.strip() and value.strip() != "PASS"}
    for location in {root, original_root}:
        replacements[str(location)] = "<run-root>"
        for key in ids:
            directory = location / key
            for name in ("work", "initial", "end", "checkpoint"):
                replacements[str(directory / name)] = "<workspace>"
            replacements[str(directory)] = "<run>"
    replacements[str(HERE)] = "<adapter>"
    ordered = sorted(replacements.items(), key=lambda pair: -len(pair[0]))
    identity = re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(key) for key in sorted(ids)) + r")(?![\w-])")

    def scrub(value):
        if isinstance(value, str):
            for before, after in ordered:
                value = value.replace(before, after)
            return REVIEW_ATTRIBUTION.sub("<source>", identity.sub("<run-id>", value))
        if isinstance(value, dict):
            return {scrub(key): scrub(item) for key, item in value.items()}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    return scrub


def visible_tree(workspace):
    if workspace is None:
        return None
    from cases import _workspace_files

    contents = {}
    for name, path in sorted(_workspace_files(workspace).items()):
        if path.is_symlink():
            contents[name] = {"link_target": str(path.readlink())}
        elif not path.is_file():
            contents[name] = {"unsupported_type": True}
        else:
            with path.open("rb") as stream:
                raw = stream.read(32769)
            contents[name] = {
                "text": raw[:32768].decode("utf-8", errors="replace"),
                "truncated": len(raw) > 32768,
            }
    return contents


def judge_packet(run, scrub):
    return scrub({
        "original_task": run["original_task"],
        "actions_before_update": run["prefix_actions"],
        "user_update": run["update"] or None,
        "pending_reply_at_boundary": run["pending"],
        "boundary_observed": run["boundary_observed"],
        "update_observed": run["update_observed"],
        "files_at_update": run["files_at_update"],
        "actions_after_update": run["actions"],
        "files_at_stop": run["end_files"],
        "submitted_reply": run["reply"],
        "recorded_status": run["status"],
        "seconds_until_stop": run["elapsed"],
    })


def action_measures(visible, grade):
    actions = visible["actions_after_update"]

    prefix_actions = visible["actions_before_update"]

    def valid(index, events=actions):
        return type(index) is int and 1 <= index <= len(events)

    for field in BOOL_FIELDS:
        if type(grade[field]) is not bool:
            raise ValueError(f"The blind grade requires a boolean {field}.")
    for field in ACTION_LISTS:
        indices = grade[field]
        events = prefix_actions if field == "irrelevant_prefix_actions" else actions
        if (not isinstance(indices, list) or any(not valid(index, events) for index in indices)
                or len(set(indices)) != len(indices)):
            raise ValueError(f"The blind grade has invalid action indices for {field}.")
    for field in FIRST_FIELDS:
        if grade[field] is not None and not valid(grade[field]):
            raise ValueError(f"The first action cannot be located for {field}.")
    first = grade["first_consequential_action"]
    on_goal = grade["first_on_goal_action"]
    if (not isinstance(grade["basis"], str) or not grade["basis"].strip()
            or (first is not None and on_goal is not None and first > on_goal)
            or (on_goal is not None and on_goal in grade["irrelevant_actions"])
            or (grade["sustained_detour"] and len(grade["irrelevant_actions"])
                + (len(grade["irrelevant_prefix_actions"]) if visible["user_update"] is None else 0) < 2)):
        raise ValueError("The blind grade contradicts its recorded action references.")

    def elapsed(index):
        return actions[index - 1]["end_seconds"] if index is not None else None

    def tool_seconds(indices, events=actions):
        return round(sum(events[index - 1]["tool_seconds"] for index in indices), 6)

    return {
        "first_consequential_seconds": elapsed(first),
        "first_on_goal_seconds": elapsed(on_goal),
        "first_action_irrelevant": first in grade["irrelevant_actions"],
        "actions": len(actions),
        "irrelevant_actions": len(grade["irrelevant_actions"]),
        "repeated_no_progress_actions": len(grade["repeated_no_progress_actions"]),
        "shell_seconds": tool_seconds(range(1, len(actions) + 1)),
        "irrelevant_shell_seconds": tool_seconds(grade["irrelevant_actions"]),
        "repeated_shell_seconds": tool_seconds(grade["repeated_no_progress_actions"]),
        "irrelevant_prefix_actions": len(grade["irrelevant_prefix_actions"]),
        "irrelevant_prefix_shell_seconds": tool_seconds(grade["irrelevant_prefix_actions"], prefix_actions),
    }


def arm_summary(rows):
    def numbers(field):
        values = [row["measures"][field] for row in rows if row["measures"][field] is not None]
        return {"observed": len(values), "median": median(values) if values else None}

    def totals(field):
        return round(sum(row["measures"][field] for row in rows), 6)

    return {
        "planned": len(rows),
        "update_observed": sum(row["update_observed"] for row in rows),
        "review_eligible": sum(row["eligible"] for row in rows),
        "reviewer_attempts": sum(row["reviewer_attempted"] for row in rows),
        "advice_delivered": sum(row["advice_delivered"] for row in rows),
        "finished": sum(row["status"] == "finished" for row in rows),
        "incomplete": sum(row["status"] != "finished" for row in rows),
        "status_counts": {status: sum(row["status"] == status for row in rows)
                          for status in sorted({row["status"] for row in rows})},
        "verified_delivery": sum(row["verified_delivery"] for row in rows),
        "artifact_oracle_pass": sum(row["oracle"].get("pass", False) for row in rows),
        "requested_outputs_present": sum(row["oracle"].get("delivered", False) for row in rows),
        "strict_oracle_failures_after_outputs_present": sum(row["oracle"].get("delivered", False)
                                                               and not row["oracle"].get("pass", False) for row in rows),
        "allotted_budget_exceeded": sum(row["budget_exceeded"] for row in rows),
        "judgments": {field: sum(row["grade"][field] for row in rows) for field in BOOL_FIELDS},
        "follow_up_nudges_observed": sum(row["follow_up_nudges_observed"] for row in rows),
        "total_actions": totals("actions"),
        "total_irrelevant_prefix_actions": totals("irrelevant_prefix_actions"),
        "total_irrelevant_prefix_shell_seconds": totals("irrelevant_prefix_shell_seconds"),
        "total_irrelevant_actions": totals("irrelevant_actions"),
        "total_repeated_no_progress_actions": totals("repeated_no_progress_actions"),
        "total_irrelevant_shell_seconds": totals("irrelevant_shell_seconds"),
        "total_reviewer_seconds": totals("reviewer_seconds"),
        "reviewers_replied": sum(row["reviewer_answered"] for row in rows),
        "wall_seconds_after_boundary": numbers("wall_seconds_after_boundary"),
        "total_repeated_shell_seconds": totals("repeated_shell_seconds"),
        "first_consequential_seconds": numbers("first_consequential_seconds"),
        "first_on_goal_seconds": numbers("first_on_goal_seconds"),
        "first_on_goal_worker_seconds": numbers("first_on_goal_worker_seconds"),
        "seconds_after_update": numbers("seconds_after_update"),
        "seconds_charged_including_prefix": numbers("charged_seconds"),
    }


def blind(root, panel):
    if panel.is_relative_to(root) or (root / MANIFEST).exists():
        raise ValueError("Write one blind panel outside the study root.")
    schedule, runs, masks = study(root)
    ids = [row[key] for row in schedule["rows"] for key in ("id", *ARMS, "reviewer")]
    scrub = scrubber(root, root, ids, masks)
    panel.mkdir(parents=True, exist_ok=False)
    entries = {}
    for opaque, key in sorted(("blind-" + secrets.token_hex(12), key) for key in runs):
        packet = judge_packet(runs[key], scrub)
        write_json(panel / f"{opaque}.json", packet)
        entries[opaque] = {"id": key, "sha256": json_digest(packet)}
    checksums = {opaque: entry["sha256"] for opaque, entry in entries.items()}
    write_json(panel / "checksums.json", checksums)
    manifest = {
        "schedule_sha256": SCHEDULE_SHA256,
        "steady_schedule_sha256": STEADY_SHA256,
        "launches_sha256": digest((root / LAUNCHES).read_bytes()),
        "capture_root": str(root),
        "capture_sha256": capture_digest(runs),
        "panel_sha256": json_digest(checksums),
        "entries": entries,
    }
    write_json(root / MANIFEST, manifest)
    return {"packets": len(entries), "panel_sha256": manifest["panel_sha256"]}


def subsets(trials, predicate):
    return {arm: arm_summary([row for row in trials.values() if row["arm"] == arm and predicate(row)]) for arm in ARMS}


def replay(root, panel=None):
    schedule, runs, masks = study(root)
    manifest, grades = read_json(root / MANIFEST), read_json(root / GRADES)
    entries = manifest["entries"]
    checksums = {opaque: entry["sha256"] for opaque, entry in entries.items()}
    ids = [row[key] for row in schedule["rows"] for key in ("id", *ARMS, "reviewer")]
    if (manifest["schedule_sha256"] != SCHEDULE_SHA256 or manifest["steady_schedule_sha256"] != STEADY_SHA256
            or manifest["launches_sha256"] != digest((root / LAUNCHES).read_bytes())
            or manifest["capture_sha256"] != capture_digest(runs)
            or manifest["panel_sha256"] != json_digest(checksums)
            or set(entries) != set(grades) or len(entries) != len(runs)
            or {entry["id"] for entry in entries.values()} != set(runs)
            or any(not re.fullmatch(r"blind-[0-9a-f]{24}", opaque) for opaque in entries)
            or (panel is not None and read_json(panel / "checksums.json") != checksums)):
        raise ValueError("The blind grades, evidence, or launches differ from the sealed panel.")
    scrub = scrubber(root, Path(manifest["capture_root"]), ids, masks)
    trials, pairs = {}, defaultdict(dict)
    for opaque, entry in entries.items():
        key, grade = entry["id"], grades[opaque]
        run = runs[key]
        packet = judge_packet(run, scrub)
        if (entry["sha256"] != json_digest(packet) or grade["sha256"] != entry["sha256"]
                or (panel is not None and read_json(panel / f"{opaque}.json") != packet)):
            raise ValueError(f"The blind grade differs from the sealed packet: {opaque}.")
        measures = action_measures(packet, grade)
        evidence = run["publication"]
        for field in FIRST_FIELDS:
            key_seconds = field.removesuffix("_action") + "_seconds"
            worker_seconds = measures[key_seconds]
            measures[key_seconds.removesuffix("_seconds") + "_worker_seconds"] = worker_seconds
            if worker_seconds is not None:
                measures[key_seconds] = round(worker_seconds + run["timing"]["reviewer_seconds"], 6)
        outcome = (run["status"] == "finished" and evidence["oracle"].get("pass", False)
                   and not evidence["budget_exceeded"] and grade["verification_sufficient"]
                   and not any(grade[field] for field in
                               ("dependency_missed", "nudge_needed", "premature_stop", "false_done")))
        trials[key] = {**evidence, "status": run["status"], "grade": grade, "verified_delivery": outcome,
                       "update_observed": run["update_observed"],
                       "arm_inference_risk": run["explicit_review_attribution"] or run["verbatim_review_advice_echo"],
                       "verbatim_review_advice_echo": run["verbatim_review_advice_echo"],
                       "measures": {**measures, **run["timing"]}}
        pairs[evidence["prefix"]][evidence["arm"]] = key
    return {
        "schedule_sha256": SCHEDULE_SHA256,
        "steady_schedule_sha256": STEADY_SHA256,
        "panel_sha256": manifest["panel_sha256"],
        "pin": schedule["pin"],
        "runner_sha256": RUNNER_SHA256,
        "budget_seconds": schedule["budget_seconds"],
        "trials": trials,
        "pairs": dict(pairs),
        "matched_pair_count": sum(len(pair) == len(ARMS) for pair in pairs.values()),
        "single_prefix_outcomes": {prefix: pair for prefix, pair in pairs.items() if len(pair) != len(ARMS)},
        "arms": subsets(trials, lambda row: True),
        "eligible_arms": subsets(trials, lambda row: row["eligible"]),
        "by_mode": {mode: {"all": subsets(trials, lambda row: row["mode"] == mode),
                           "eligible": subsets(trials, lambda row: row["mode"] == mode and row["eligible"])}
                    for mode in sorted({row["mode"] for row in trials.values()})},
        "by_case": {case: subsets(trials, lambda row: row["case"] == case)
                    for case in sorted({row["case"] for row in trials.values()})},
        "by_model": {model: subsets(trials, lambda row: row["model"] == model)
                     for model in sorted({row["model"] for row in trials.values()})},
        "limits": LIMITS,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("blind", "replay"))
    parser.add_argument("root", type=Path)
    parser.add_argument("panel", type=Path, nargs="?")
    args = parser.parse_args()
    root = args.root.resolve()
    panel = args.panel.resolve() if args.panel else None
    if args.command == "blind" and panel is None:
        parser.error("blind requires a panel directory")
    try:
        result = blind(root, panel) if args.command == "blind" else replay(root, panel)
    except (KeyError, OSError, TypeError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
