"""Replay the sealed design evidence and generated artifacts in a scratch checkout."""
import argparse
import csv
import io
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

parser = argparse.ArgumentParser(description="Recompute artifacts from design-slice checkouts on temporary copies.")
parser.add_argument("study", type=Path)
root = parser.parse_args().study.resolve()
suite = Path(__file__).resolve().parent

from design_slice_run import fixture
from long_run import workspace_tree
from proof import json_digest
from trial import digest

def read_json(path):
    return json.loads(path.read_text())

def run(work, argv):
    result = subprocess.run([sys.executable, '-I', '-B', *argv], cwd=work,
                            capture_output=True, text=True, timeout=5, check=True)
    return result.stdout

schedule_path = root / 'design_slice_schedule.json'
assert schedule_path.read_bytes() == (suite / schedule_path.name).read_bytes()
schedule = read_json(schedule_path)
for name, expected in schedule['case_sha256'].items():
    assert digest((suite / name).read_bytes()) == expected, name

cohorts = {}
states = {}
for row in schedule['rows']:
    arms = {'baseline': row['baseline'], 'candidate': row['candidate'], 'unforked': row['id']}
    for arm, trial_id in arms.items():
        parent = root / trial_id
        if not (parent / 'end.json').exists():
            continue
        case = row['case']
        f = fixture(case)
        assert (parent / 'task.txt').read_text() == f.history(case).rstrip() + '\n'
        end = read_json(parent / 'end.json')
        recorded = read_json(parent / 'end-workspace.json')
        assert workspace_tree(parent / 'work') == recorded
        assert json_digest(recorded) == end['workspace_sha256']
        assert digest((parent / 'events.jsonl').read_bytes()) == end['trace_sha256']
        assert digest((parent / 'reply.txt').read_bytes()) == end['reply_sha256']
        original = read_json(parent / 'initial-workspace.json')
        delta = [key for key in sorted(set(original) | set(recorded)) if original.get(key) != recorded.get(key)]
        with TemporaryDirectory(prefix='design-independent-audit-') as tmp:
            work = Path(tmp) / 'work'
            shutil.copytree(parent / 'work', work, symlinks=True)
            assert workspace_tree(work) == recorded
            grade = f.grade(work, case)
            if case == 'preview':
                expect = read_json(work / f.COVERAGE)['cases']
                capture_outcomes = []
                for entry in expect:
                    trace = json.loads(run(work, [f.TRACE, entry['capture']]))
                    assert trace.pop('capture') == read_json(work / entry['capture'])['capture']
                    assert trace == entry['expect'], (trial_id, entry)
                    capture_outcomes.append({'path': entry['capture'], **trace})
                extra = {'capture_matches': len(capture_outcomes), 'captures': capture_outcomes}
            else:
                assert (work / f.RENDERER).read_text() == f.RENDER
                assert (work / f.PROBE).read_text() == f.DEMO
                page_message = run(work, [f.RENDERER, '--check'])
                coverage = list(csv.DictReader(io.StringIO((work / f.COVERAGE).read_text()), strict=True))
                acceptance = list(csv.DictReader(io.StringIO((work / f.ACCEPTANCE).read_text()), strict=True))
                assert len(coverage) == len(acceptance) == 3
                assert [(r['id'], r['status']) for r in coverage] == [(f'C0{i}', 'covered') for i in (1,2,3)]
                assert [(r['id'], r['status']) for r in acceptance] == [(f'A0{i}', 'ready') for i in (1,2,3)]
                assert all(None not in r and None not in r.values() for r in coverage + acceptance)
                opening = read_json(work / f.OPENING)
                draft = (work / f.DRAFT).read_text()
                assert (work / f.OPENING).read_text() == f._opening(case)[f.OPENING]
                assert f._qualified(opening) == (case == 'ledger_ready')
                logs = [json.loads(line) for line in (work / f.PROBE_LOG).read_text().splitlines()]
                evidence_files = {}
                for line in logs:
                    saved, receipt = line['saved'], line['receipt']
                    expected = f.RECHECK if receipt['scenario'] == 'delayed' else 'evidence/' + receipt['scenario'] + '-probe.json'
                    assert saved == expected and saved not in evidence_files and read_json(work / saved) == receipt
                    evidence_files[saved] = receipt
                    assert all(i in draft for i in receipt['request_ids']) and saved in draft
                    assert re.search(r'\b' + str(receipt['delay_seconds']) + r'\b', draft)
                assert f._qualified(evidence_files[f.RECHECK])
                assert f.RECHECK in acceptance[1]['evidence']
                assert workspace_tree(work) == recorded
                for receipt in [opening, *evidence_files.values()]:
                    args = [f.PROBE, receipt['scenario'], '--delay', str(receipt['delay_seconds'])]
                    for identifier in receipt['request_ids']:
                        args += ['--request-id', identifier]
                    assert json.loads(run(work, args)) == receipt, (trial_id, receipt)
                extra = {'renderer_check': page_message.strip(), 'probe_replays': len(evidence_files),
                         'probe_outcomes': evidence_files, 'opening_replay': opening,
                         'coverage_csv_rows': len(coverage), 'acceptance_csv_rows': len(acceptance)}
        counts = cohorts.setdefault((case, arm), Counter())
        counts.update({'states': 1})
        counts.update({k: int(v) for k, v in grade.items() if type(v) is bool})
        counts.update({k: int(v) for k, v in grade.get('evidence', {}).get('checks', {}).items()})
        if 'preservation' in grade:
            counts.update({'preserved': int(grade['preservation']['passed'])})
        states[trial_id] = {'case': case, 'arm': arm, 'model': row['model'], 'grade': grade,
                            'tree_delta': delta, **extra}
assert len(states) == 11
print(json.dumps({'count': len(states),
                  'cohorts': {' '.join(k): dict(v) for k, v in cohorts.items()},
                  'runs': states}, indent=2))
