"""Combine blind reader judgments with independent verified queue state."""
import argparse
import json
import statistics
import tempfile
from pathlib import Path

from backlog_verify import replay
from proof import read_json
from trial import digest


def validate(condition, message):
    if not condition:
        raise ValueError(message)


def observed_median(values):
    observed = [v for v in values if v is not None]
    return statistics.median(observed) if observed else None


def grade(root, panel, key_file, grade_file):
    assigned = read_json(key_file)
    grades = read_json(grade_file)
    with tempfile.TemporaryDirectory() as temp:
        restored = Path(temp) / 'packets'
        study = replay(root, blind=restored)
        restored_key = read_json(restored.with_name(restored.name + '.key.json'))
        by_id = {ident: label for label, ident in restored_key.items()}
        validate(set(assigned) == set(grades) and set(assigned.values()) == set(by_id)
                 and len(assigned) == len(by_id), 'The grades and packets must cover all subjects.')
        scored = {}
        for label, ident in assigned.items():
            packet_file = panel / (label + '.json')
            packet_bytes = packet_file.read_bytes()
            validate(packet_bytes == (restored / (by_id[ident] + '.json')).read_bytes(),
                     f'Archived blind packet for {ident} differs from the fresh reconstruction.')
            response = grades[label]
            validate(response['packet_sha256'] == digest(packet_bytes), 'Grade packet digest mismatch.')
            packet = read_json(packet_file)
            actions = packet['actions']
            for key in ('cause_and_scope_correct', 'delivery_claim_supported', 'user_nudge_needed',
                        'missed_dependency', 'scope_violation_attempt'):
                validate(type(response[key]) is bool, 'Expected boolean ' + key)
            for key in ('first_consequential', 'first_useful'):
                idx = response[key]
                validate(idx is None or (type(idx) is int and 1 <= idx <= len(actions)), 'Invalid index for ' + key)
            for idx in response['avoidable_repeats']:
                validate(type(idx) is int and 1 <= idx <= len(actions), 'Invalid repeat index.')
            validate(isinstance(response['basis'], str) and response['basis'].strip(), 'Missing basis.')
            idx = response['first_useful']
            scored[ident] = {**response, 'first_useful_seconds': actions[idx-1]['end_seconds'] if idx else None}
    report = []
    for pair in study['pairs']:
        item = {'case': pair['case']}
        for arm in ('baseline', 'candidate'):
            proof = pair[arm]
            if proof['run_id'] not in scored:
                item[arm] = {'id': proof['run_id'], 'status': proof['status'], 'passed': False,
                             'seconds': None, 'artifact': None, 'reader': None}
                continue
            reader = scored[proof['run_id']]
            passed = (proof['completion'] and reader['cause_and_scope_correct']
                      and reader['delivery_claim_supported'] and not reader['user_nudge_needed']
                      and not reader['missed_dependency'] and not reader['scope_violation_attempt'])
            item[arm] = {'id': proof['run_id'], 'passed': passed, 'seconds': proof.get('elapsed_seconds'),
                         'artifact': proof.get('artifact'), 'reader': reader}
        report.append(item)
    summary = {}
    for arm in ('baseline', 'candidate'):
        trials = [pair[arm] for pair in report]
        summary[arm] = {
            'trials': len(trials), 'passed': sum(t['passed'] for t in trials),
            'durable_passes': sum(t['artifact']['passed'] for t in trials if t['artifact']),
            'nudges_judged_necessary': sum(t['reader']['user_nudge_needed'] for t in trials if t['reader']),
            'correct_scope_and_cause': sum(t['reader']['cause_and_scope_correct'] for t in trials if t['reader']),
            'median_active_seconds': observed_median(t['seconds'] for t in trials),
            'median_first_useful_seconds': observed_median(
                t['reader']['first_useful_seconds'] for t in trials if t['reader']),
        }
    return {'summary': summary, 'pairs': report}


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ('root','panel','key','grades'):
        cli.add_argument(name, type=Path)
    args = cli.parse_args()
    print(json.dumps(grade(args.root, args.panel, args.key, args.grades), indent=2, sort_keys=True))
