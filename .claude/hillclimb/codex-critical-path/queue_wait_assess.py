"""Reproduce first-pass field-queue judgments, including legitimate escalation."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

import backlog_assess
import queue_wait_run


def grade(root, panel, key, grades):
    with patch.object(backlog_assess, 'replay', queue_wait_run.replay):
        report = backlog_assess.grade(root, panel, key, grades)
    for arm in ('baseline', 'candidate'):
        trials = [row[arm] for row in report['pairs']]
        for trial in trials:
            if trial['reader'] is None:
                continue
            reader = trial['reader']
            for field in ('blocker_actionable', 'false_done'):
                backlog_assess.validate(type(reader[field]) is bool, f'Expected boolean {field}.')
            trial['passed'] = trial['passed'] and reader['blocker_actionable'] and not reader['false_done']
        judged = [row['reader'] for row in trials if row['reader']]
        report['summary'][arm].update(
            passed=sum(row['passed'] for row in trials),
            actionable_blocker_routing=sum(r['blocker_actionable'] for r in judged),
            false_completion=sum(r['false_done'] for r in judged),
            genuine_dependencies_missed=sum(r['missed_dependency'] for r in judged),
            scope_violation_attempts=sum(r['scope_violation_attempt'] for r in judged),
        )
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'panel', 'key', 'grades'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    print(json.dumps(grade(args.root, args.panel, args.key, args.grades), indent=2, sort_keys=True))
