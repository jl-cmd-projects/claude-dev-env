"""Audit every terminal nomination and the cost of actual reviewer dispatch."""
import argparse
import json
import statistics
from pathlib import Path

import queue_wait_recover as recovery
from backlog_verify import require
from proof import read_json, read_text
from trial import digest


def audit(root):
    schedule = read_json(root / 'queue_wait_schedule.json')
    launches = read_json(root / 'review-launches.json')
    template = read_text(root / 'review-dispatch.txt')
    require(template.count('{id}') == 1, 'Invalid reviewer dispatch template.')
    expected = set()
    rows = []
    for pair in schedule['rows']:
        row = {'case': pair['case']}
        for arm in ('baseline', 'candidate'):
            ident = pair[arm]
            first = root / ident
            prefix = recovery.first_pass(first)
            selection = prefix['selection']
            reviewer = 'r_' + ident
            review_dir = root / 'reviews' / reviewer
            elapsed = prefix['marker']['elapsed_seconds']
            review_seconds = 0
            advice = None
            if arm == 'candidate' and selection['eligible']:
                expected.add(reviewer)
                launch = launches[reviewer]
                require(launch['model'] == 'gpt-6.2-sol' and launch['reasoning_effort'] == 'high'
                        and launch['fork_turns'] == 'none'
                        and launch['receipt']['task_name'] == '/root/' + reviewer
                        and launch['dispatch_sha256'] == digest(template.replace('{id}', reviewer).encode()),
                        'Invalid reviewer launch receipt.')
                require(read_json(review_dir / 'receipt.json')['session'] == reviewer, 'Wrong receipt session.')
                advice, _, review_seconds = recovery.review_result(prefix, review_dir)
            journal = read_json(first / 'end' / 'queue-state' / 'events.json')
            idle_watches = [e['command']['minutes'] for e in journal
                            if e['action'] == 'watch' and e['outcome'].get('result', {}).get('entries') == []]
            row[arm] = {
                'id': ident, 'nominated': selection['eligible'], 'reasons': selection['reasons'],
                'ambiguities': selection['ambiguities'], 'selection_receipt': selection.get('receipt'),
                'worker_seconds': elapsed, 'review_seconds': review_seconds,
                'response': (advice or 'PASS') if review_seconds else None,
                'needs_continuation': advice is not None,
                'worker_plus_review_seconds': elapsed + review_seconds,
                'empty_queue_watches': len(idle_watches), 'empty_queue_simulated_minutes': sum(idle_watches),
            }
        row['paired_active_difference_seconds'] = (
            row['candidate']['worker_plus_review_seconds'] - row['baseline']['worker_seconds']
        )
        rows.append(row)
    require(set(launches) == expected == {p.name for p in (root / 'reviews').iterdir() if p.is_dir()},
            'Recorded reviews differ from nominated policy launches.')
    return {
        'pairs': rows,
        'review_calls': len(expected),
        'review_seconds': sum(r['candidate']['review_seconds'] for r in rows),
        'advice_responses': sum(r['candidate']['needs_continuation'] for r in rows),
        'median_paired_active_difference_seconds': statistics.median(r['paired_active_difference_seconds'] for r in rows),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    print(json.dumps(audit(parser.parse_args().root.resolve()), indent=2, sort_keys=True))
