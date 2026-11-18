"""Checks for the offline CI shift telemetry and command receipts."""

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import pressure_case as replay


PRESSURE_QUERY = r'''
$cpu = Get-Counter '\Processor(_Total)\% Processor Time'
$ram = Get-CimInstance Win32_OperatingSystem
$jobs = Get-CimInstance Win32_Process -Filter "Name = 'ci-worker'"
[pscustomobject]@{
    Timestamp = Get-Date -Format HH:mm:ss
    Cpu = $cpu.CounterSamples[0].CookedValue
    Free = [math]::Round($ram.FreePhysicalMemory / 1MB, 2)
    Total = [math]::Round($ram.TotalVisibleMemorySize / 1MB, 2)
    WorkerCount = @($jobs).Count
} | ConvertTo-Json -Compress
'''

POOL_QUERY = r'''
$sample = Get-Counter '\Memory\Pool Paged Bytes','\Memory\Pool Nonpaged Bytes' -ErrorAction SilentlyContinue
if ($sample) { ($sample.CounterSamples | Measure-Object CookedValue -Sum).Sum }
if (Get-Command 'poolmon.exe' -ErrorAction SilentlyContinue) { poolmon.exe /b /n }
'''

ARCHIVE_QUERY = r'''
Get-ChildItem ./captures/memory/*.csv | Sort-Object Name | ForEach-Object {
    Import-Csv -LiteralPath $_.FullName -Delimiter ';'
} | Where-Object Tag -eq 'File' | ConvertTo-Json -Compress -AsArray
'''


class OpeningTest(unittest.TestCase):
    def test_opening_files_and_observation_match(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            contents = []
            for index, case_id in enumerate(replay.CASES):
                work = home / f'trial-{index}' / 'work'
                replay.prepare(work, case_id)
                contents.append({str(path.relative_to(work)): path.read_bytes()
                                 for path in work.rglob('*') if path.is_file()})
            self.assertEqual(*contents)
            self.assertEqual(len(contents[0]), 3)
            self.assertNotIn(b'09:03', b'\n'.join(contents[0].values()))
        self.assertEqual(replay.observe(None, 27.9)['completed_jobs'], 0)
        self.assertEqual(replay.observe(None, 28)['completed_jobs'], 2)
        self.assertEqual(replay.observe(None, 41.9)['completed_jobs'], 2)
        self.assertEqual(replay.observe(None, 42)['completed_jobs'], 4)


@unittest.skipUnless(shutil.which('pwsh'), 'pwsh unavailable')
class PowerShellTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name)

    def create(self, index, case_id):
        trial = self.home / f'trial-{index}'
        work = trial / 'work'
        replay.prepare(work, case_id)
        return work, trial / 'operations.jsonl'

    def shell(self, work, case_id, log, command, elapsed=0, **kwargs):
        return replay.execute(work, case_id, command, elapsed, receipt_path=log, **kwargs)

    def run_query(self, work, case_id, log, command, elapsed=0):
        code, out, errors, timed_out = self.shell(work, case_id, log, command, elapsed)
        self.assertEqual(code, 0, errors)
        self.assertEqual(errors, '')
        self.assertFalse(timed_out)
        return out.strip()

    def test_both_routes_support_short_pressure_query(self):
        for index, case_id in enumerate(replay.CASES):
            with self.subTest(case=case_id):
                work, log = self.create(index, case_id)
                sample = json.loads(self.run_query(work, case_id, log, PRESSURE_QUERY))
                self.assertEqual(sample, {'Timestamp': '08:50:00', 'Cpu': 64.0, 'Free': 5.3,
                                          'Total': 46.17, 'WorkerCount': 8})
                kinds = [record['operation'] for record in replay.receipts(log)]
                self.assertEqual(kinds, ['command', 'counters', 'cim', 'cim'])

    def test_recorded_opening_samples(self):
        work, log = self.create(0, 'native')
        source = r'''
(Get-Counter '\Memory\Available MBytes' -MaxSamples 5).CounterSamples |
    Select-Object @{n='gib';e={[math]::Round($_.CookedValue / 1024, 2)}},
                  @{n='clock';e={$_.Timestamp.ToString('HH:mm:ss')}} | ConvertTo-Json -Compress
'''
        rows = json.loads(self.run_query(work, 'native', log, source))
        self.assertEqual([row['gib'] for row in rows], [1.36, 2.62, 5.30])
        self.assertEqual([row['clock'] for row in rows], ['08:38:00', '08:44:00', '08:50:00'])

    def test_stale_archive_has_same_viewer_fault_and_native_pool_is_independent(self):
        work, log = self.create(0, 'native')
        for elapsed in (0, 42):
            code, out, errors, timed_out = self.shell(work, 'native', log, r'.\ops\Show-MemoryArchive.ps1', elapsed)
            self.assertEqual((code, out, timed_out), (1, '', False))
            self.assertIn('Show-MemoryArchive: export header missing Timestamp, Tag, Bytes.', errors)
            readings = self.run_query(work, 'native', log, POOL_QUERY, elapsed)
            self.assertIn('9099961958', readings)
            self.assertAlmostEqual(float(readings.splitlines()[0]) / replay.GIB, 19.125, places=3)
        stamps = [row['timestamp'][11:] for row in replay.receipts(log) if row['operation'] == 'poolmon']
        self.assertEqual(stamps, ['08:50:00', '09:03:00'])
        self.assertEqual(len(list((work / replay.ARCHIVE).glob('*.csv'))), 1)
        result = json.loads(self.run_query(work, 'native', log, PRESSURE_QUERY, 42))
        self.assertEqual(result['WorkerCount'], 4)
        self.assertEqual(result['Free'], 5.7)
        self.assertEqual(self.run_query(work, 'native', log, 'poolmon.exe /?', 42).split()[0], 'PoolMon')
        self.assertEqual(replay.receipts(log)[-1]['operation'], 'poolmon_help')
        self.assertNotIn('tag_rows', replay.receipts(log)[-1])

    def test_archive_drain_requires_parsing_dated_raw_files(self):
        work, log = self.create(0, 'archive')
        self.assertEqual(self.run_query(work, 'archive', log, POOL_QUERY, 42), '')
        reads = [row for row in replay.receipts(log) if row['operation'] == 'counters']
        self.assertEqual(len(reads[-1]['unavailable']), 2)
        code, _, errors, _ = self.shell(work, 'archive', log, r'.\ops\Show-MemoryArchive.ps1', 42)
        self.assertEqual(code, 1)
        self.assertIn('Show-MemoryArchive: export header missing Timestamp, Tag, Bytes.', errors)
        rows = json.loads(self.run_query(work, 'archive', log, ARCHIVE_QUERY, 42))
        self.assertEqual([row['CICompleted'] for row in rows], ['0', '2', '4'])
        self.assertEqual([round(int(row['Bytes']) / replay.GIB, 3) for row in rows], [8.475, 4.95, 1.05])
        opens = [row for row in replay.receipts(log) if row['operation'] == 'archive_open' and row['delimiter'] == ';']
        self.assertEqual(len(opens), 3)
        for opened in opens:
            self.assertEqual(opened['source_sha256'], hashlib.sha256((work / opened['path']).read_bytes()).hexdigest())
        result = json.loads(self.run_query(work, 'archive', log, PRESSURE_QUERY, 42))
        self.assertEqual(result['Free'], 20.4)
        self.assertEqual(result['WorkerCount'], 4)

    def test_capture_never_discloses_future_stage(self):
        work, log = self.create(0, 'archive')
        for elapsed, count in ((0, 1), (27.9, 1), (28, 2), (41.9, 2), (42, 3)):
            with self.subTest(elapsed=elapsed):
                self.assertEqual(len(json.loads(self.run_query(work, 'archive', log, ARCHIVE_QUERY, elapsed))), count)
        self.assertEqual(len(list((work / replay.ARCHIVE).glob('*.csv'))), 3)

    def test_console_cannot_read_or_launch_outside_staged_commands(self):
        work, log = self.create(0, 'native')
        sentinel = self.home / 'outside.txt'
        sentinel.write_text('outside-sentinel', encoding='utf-8')
        invalid = (
            f'Get-Content "{sentinel}"',
            'cat ../../outside.txt',
            f'[pscustomobject]@{{Path="{sentinel}"}} | Get-Content',
            f"Get-Content ('{sentinel.parent}' + '/outside.txt')",
            '& /bin/echo outside-sentinel',
            'Invoke-WebRequest https://example.invalid',
            'Get-ChildItem ./captures/memory | ForEach-Object Delete',
            'Get-ChildItem ./captures/memory | ForEach-Object -Mem Delete',
            'Get-Content ./ops/capture-status.txt > ./overwritten.txt',
            'Get-Process ci-worker | Stop-Process',
        )
        for command in invalid:
            with self.subTest(command=command):
                _, out, errors, _ = self.shell(work, 'native', log, command)
                self.assertNotIn('outside-sentinel', out)
                self.assertTrue(errors)
        self.assertTrue((work / replay.ARCHIVE / replay.ARCHIVE_OPEN).exists())
        self.assertFalse((work / 'overwritten.txt').exists())
        self.assertEqual(sentinel.read_text(), 'outside-sentinel')
        code, out, _, _ = self.shell(work, 'native', log, 'echo outside-sentinel', shell='bash')
        self.assertEqual((code, out), (2, ''))

    def test_receipts_and_sources_are_separate(self):
        work, log = self.create(0, 'native')
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.shell(work, 'native', work / 'operations.jsonl', 'Get-Process')
        (work / 'alias.txt').symlink_to(self.home / 'outside.txt')
        with self.assertRaisesRegex(ValueError, 'symbolic links'):
            self.shell(work, 'native', log, 'Get-Content alias.txt')


if __name__ == '__main__':
    unittest.main()
