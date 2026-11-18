"""Reproduce the five frozen structural and attribution failures on temporary checkouts."""
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from long_run import workspace_tree
from pivot_run import action_changes
from proof import json_digest

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("study", type=Path)
parser.add_argument("summary", type=Path)
args = parser.parse_args()
ROOT = args.study.resolve()
ORACLE = json.loads(args.summary.read_text())['trials']
WRAPPERS = {'v68636': 5, 'v44014': 6, 'v78346': 3}
CHECKPOINTS = {p.joinpath('checkpoint-workspace.json').read_bytes(): p/'work' for p in ROOT.glob('q*')}
PROBE_LOG = 'evidence/probe-runs.jsonl'
SIG = hashlib.sha256

def replay(trial):
    folder = ROOT/trial
    trace = [json.loads(line) for line in (folder/'events.jsonl').read_text().splitlines()]
    opening = CHECKPOINTS[(folder/'checkpoint-workspace.json').read_bytes()]
    with TemporaryDirectory(prefix='pending-mechanics-audit-') as scratch:
        work = Path(scratch)/'work'
        shutil.copytree(opening, work, symlinks=True)
        for event in trace:
            before = workspace_tree(work)
            initial_log = (work/PROBE_LOG).read_bytes()
            result = subprocess.run(['bash','-c',event['command']], cwd=work, capture_output=True,
                                    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'), timeout=10)
            after = workspace_tree(work)
            assert result.returncode == event['exit'], (trial,event['action'],result.stderr)
            assert json_digest(before) == event['before_sha256'], (trial,event['action'],'before')
            assert action_changes(before,after) == event['changes'], (trial,event['action'],'delta')
            assert json_digest(after) == event['after_sha256'], (trial,event['action'],'after')
            if event['action'] != 1 or trial not in ('v16017','v39976'):
                assert result.stdout == event['stdout'].encode(), (trial,event['action'],'stdout')
                assert result.stderr == event['stderr'].encode(), (trial,event['action'],'stderr')
            if event['action'] == WRAPPERS.get(trial):
                raw = (work/PROBE_LOG).read_bytes()
                archived = (folder/'work'/PROBE_LOG).read_bytes()
                assert raw == archived and raw.startswith(initial_log)
                log_delta = raw[len(initial_log):]
                print(trial, 'action', event['action'], 'stdout/stderr/whole delta matched',
                      'log +bytes/sha', len(log_delta), SIG(log_delta).hexdigest(),
                      'final log sha', SIG(raw).hexdigest())
                for line in log_delta.splitlines(keepends=True):
                    entry = json.loads(line)
                    row = entry['receipt']
                    argv = ['python','-B','tools/ledger_demo.py',row['scenario'],'--delay',str(row['delay_seconds'])]
                    for transport_id in row['request_ids']:
                        argv.extend(('--request-id',transport_id))
                    if entry['saved']:
                        argv.append('--save')
                    current = (work/PROBE_LOG).read_bytes()
                    direct = subprocess.run(argv,cwd=work,capture_output=True,check=True,timeout=10)
                    assert (work/PROBE_LOG).read_bytes() == current + line
                    if entry['saved']:
                        assert direct.stdout == (folder/'work'/entry['saved']).read_bytes()
                        assert (work/entry['saved']).read_bytes() == direct.stdout
                    else:
                        assert direct.stdout == (json.dumps(row,indent=2,sort_keys=True)+'\n').encode()
                    (work/PROBE_LOG).write_bytes(current)
                    print('  ', row['scenario'], row['request_ids'], row['delay_seconds'],
                          row['second_outcome'], row['ledger_rows'], 'saved=', entry['saved'])
        assert workspace_tree(work) == json.loads((folder/'end-workspace.json').read_text())
        for item in work.rglob('*'):
            if item.is_file():
                assert item.read_bytes() == (folder/'work'/item.relative_to(work)).read_bytes()
        checks = ORACLE[trial]['artifact_audit']['checks']
        if not checks['acceptance_csv']:
            with (work/'review/acceptance.csv').open(newline='') as stream:
                reader = csv.DictReader(stream, strict=True)
                rows = list(reader)
                assert reader.fieldnames == ['id','status','check','evidence']
            counts = Counter(row['id'] for row in rows)
            assert all(counts[name]==1 for name in ('A01','A02','A03'))
            assert all(count == 1 for count in counts.values())
            assert all(None not in row and all(value and value.strip() for value in row.values())
                       and row['status'] == 'ready' for row in rows)
            assert all((work/path.split('#')[0]).is_file() for row in rows
                       for path in re.split(r'\s*[|;]\s*',row['evidence']))
            rows_by_id = {row['id']: row for row in rows}
            print(trial, 'strict parse passed, required rows present once with status ready',
                  'extra IDs/evidence:', [(name, row['evidence']) for name, row in rows_by_id.items()
                                           if name not in ('A01','A02','A03')])
            assert subprocess.run(['python','-B','tools/render_review.py','--check'],cwd=work,
                                  capture_output=True,check=True).stdout.endswith(b'three source artifacts\n')

os.umask(0o077)
for trial in ('v16017','v68636','v44014','v78346','v39976'):
    replay(trial)
print('Five scratch replays matched final checkout bytes and action state hashes.')
