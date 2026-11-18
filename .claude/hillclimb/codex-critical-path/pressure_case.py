"""Offline CI shift replay with a time-gated local Windows telemetry adapter.

The opening available-memory trend and stable larger process samples are field-derived,
with amounts scaled by 0.75 and modified counts. The retention branch also models the
shape of a later observed pool and process split. Timestamps, host capacity, process and
job identities, the exporter fault, intermediate samples, and the drain branch are
reconstructed. The replay does not establish a specific driver or a memory leak.
"""

import csv
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from textwrap import dedent


CASES = ('native', 'archive')
GIB = 1024 ** 3
MIB = 1024 ** 2
TRANSITIONS = (28, 42)
ARCHIVE = 'captures/memory'
VIEWER = 'ops/Show-MemoryArchive.ps1'
CAPTURE_STATUS = 'ops/capture-status.txt'
OPENING = (
    ('08:38:00', 1.36, 6, 0, 54, 18.88, 8.27),
    ('08:44:00', 2.62, 8, 0, 66, 19.05, 8.42),
    ('08:50:00', 5.30, 8, 0, 64, 19.125, 8.475),
)
FOLLOW_UP = {
    'native': (
        ('08:57:00', 5.55, 6, 2, 52, 19.04, 8.42),
        ('09:03:00', 5.70, 4, 4, 41, 19.125, 8.475),
    ),
    'archive': (
        ('08:57:00', 11.70, 6, 2, 52, 12.85, 4.95),
        ('09:03:00', 20.40, 4, 4, 41, 3.90, 1.05),
    ),
}
DATE = '2026-04-19'
ARCHIVE_OPEN = '20260419-0850.csv'

VIEWER_SOURCE = dedent(r'''
    param([string]$Path)

    if (!$Path) {
        $directory = Join-Path (Split-Path -Parent $PSScriptRoot) 'captures/memory'
        $Path = Get-ChildItem -LiteralPath $directory -Filter '*.csv' |
            Sort-Object Name -Descending | Select-Object -First 1 -ExpandProperty FullName
    }

    $rows = @(Import-Csv -LiteralPath $Path)
    $columns = $rows[0].PSObject.Properties.Name
    if (@('Timestamp', 'Tag', 'Bytes' | Where-Object { $_ -notin $columns }).Count) {
        throw 'Show-MemoryArchive: export header missing Timestamp, Tag, Bytes.'
    }
    $rows
''').lstrip()

CAPTURE_OPEN = dedent('''
    08:38:00  Performance sample written. CI active: 6.
    08:44:00  Performance sample written. CI active: 8.
    08:50:00  Performance sample written. CI active: 8.
    08:50:10  Memory capture sync wrote captures/memory/20260419-0850.csv.
''').lstrip()


def source_sample(row, case_id):
    clock, available, workers, completed, cpu, pool, file_objects = row
    other_nonpaged = (pool - file_objects) * 0.24
    nonpaged = file_objects + other_nonpaged
    tags = [
        ('File', 'Nonp', file_objects),
        ('Ntff', 'Nonp', other_nonpaged * 0.61),
        ('Io  ', 'Nonp', other_nonpaged * 0.39),
        ('MmSt', 'Paged', (pool - nonpaged) * 0.58),
        ('CM31', 'Paged', (pool - nonpaged) * 0.42),
    ]
    pool_rows = [{'Tag': tag, 'Type': kind, 'Bytes': round(amount * GIB)} for tag, kind, amount in tags]
    timestamp = f'{DATE}T{clock}'
    memory = {
        'AvailableMBytes': round(available * 1024),
        'AvailableBytes': round(available * GIB),
        'CommittedBytes': round((57 - available * 0.72) * GIB),
        'CommitLimit': 72 * GIB,
        'PagesPersec': 9 if completed < 4 else 4,
        'PagesInputPersec': 1,
        'PagesOutputPersec': 0,
        'PageFaultsPersec': 130 if completed < 4 else 72,
        'PercentCommittedBytesInUse': round((57 - available * 0.72) / 72 * 100),
    }
    if case_id == 'native':
        memory.update({
            'PoolPagedBytes': sum(tag['Bytes'] for tag in pool_rows if tag['Type'] == 'Paged'),
            'PoolNonpagedBytes': sum(tag['Bytes'] for tag in pool_rows if tag['Type'] == 'Nonp'),
        })
    processes = [
        ('System', 4, 0, 23, 23, 1.5),
        ('ci-service', 960, 4, 72, 91, 1.1),
        ('build-python', 1476, 960, 17, 10, 5.6),
        ('container-host', 1550, 4, 137, 266, 4.6),
        ('editor-worker', 2112, 4, 536, 615, 2.6),
        ('desktop-helper', 2680, 4, 82, 122, 1.7),
        ('editor-worker', 2992, 4, 850, 1642, 0.3),
        ('editor-worker', 3120, 4, 1234, 1519, 0.8),
        ('vm-host', 3316, 4, 703, 1227, 0.4),
        ('desktop-client', 3544, 4, 1072, 1201, 1.2),
        ('browser-worker', 3756, 4, 112, 1169, 0.2),
        ('build-python', 3796, 960, 58, 812, 0.7),
        ('build-python', 3916, 960, 66, 811, 0.5),
    ]
    if clock == OPENING[0][0]:
        processes.append(('file-index', 3992, 4, 1464, 1546, 0.1))
    hours, minutes, seconds = map(int, clock.split(':'))
    host_seconds = (hours * 60 + minutes) * 60 + seconds - 31080
    for index in range(workers):
        parent = 4200 + index * 36
        processes.extend([
            ('ci-worker', parent, 960, 98 + index % 4, 120 + index % 4, 0.7),
            ('ci-task', parent + 4, parent, 169 + index % 3, 188 + index % 3, 1.8),
        ])
    return {
        'timestamp': timestamp,
        'cpu': cpu,
        'queue': 2 if cpu > 50 else 0,
        'pagefile_usage': 14 if completed < 4 else 13,
        'disk_queue': 0.5 if completed < 4 else 0.2,
        'memory': memory,
        'workers': workers,
        'completed': completed,
        'total_bytes': round(46.17 * GIB),
        'processes': [
            {'Id': pid, 'ProcessId': pid, 'ParentProcessId': ppid, 'Name': name,
             'ProcessName': name, 'WorkingSet': rss * MIB, 'WorkingSet64': rss * MIB,
             'WorkingSetSize': rss * MIB, 'PrivateMemorySize64': private * MIB,
             'CPU': round(100 + pid % 190 + host_seconds * process_cpu * 24 / 100, 2),
             'CpuPercent': process_cpu, 'HandleCount': 120 + pid % 33}
            for name, pid, ppid, rss, private, process_cpu in processes
        ],
        'pool': pool_rows,
    }


def count_visible(elapsed_seconds):
    return sum(elapsed_seconds >= transition for transition in TRANSITIONS)


def samples(case_id, elapsed_seconds):
    return [source_sample(row, case_id) for row in (*OPENING, *FOLLOW_UP[case_id][:count_visible(elapsed_seconds)])]


def write_archive(path, sample):
    with path.open('x', encoding='utf-8', newline='') as output:
        columns = ('Timestamp', 'Tag', 'Type', 'Bytes', 'CIActive', 'CICompleted')
        writer = csv.DictWriter(output, columns, delimiter=';')
        writer.writeheader()
        for tag in sample['pool']:
            writer.writerow({
                **tag, 'Timestamp': sample['timestamp'],
                'CIActive': sample['workers'], 'CICompleted': sample['completed'],
            })


def prepare(workspace, case_id):
    """Create the identical opening files for either replay."""
    if case_id not in CASES:
        raise ValueError(f'Unknown replay: {case_id}')
    workspace = Path(workspace)
    (workspace / ARCHIVE).mkdir(parents=True)
    (workspace / VIEWER).parent.mkdir()
    (workspace / VIEWER).write_text(VIEWER_SOURCE, encoding='utf-8')
    (workspace / CAPTURE_STATUS).write_text(CAPTURE_OPEN, encoding='utf-8')
    write_archive(workspace / ARCHIVE / ARCHIVE_OPEN, source_sample(OPENING[-1], 'archive'))


def observe(workspace, elapsed_seconds):
    """Return clock and CI status without loading or reporting diagnostic measurements."""
    visible = count_visible(elapsed_seconds)
    clock, _, workers, completed, *_ = FOLLOW_UP['native'][visible - 1] if visible else OPENING[-1]
    return {
        'status': f'Console replay at {clock}. CI active: {workers}. Batch jobs completed: {completed}.',
        'timestamp': f'{DATE}T{clock}', 'completed_jobs': completed,
    }


def refresh_capture(workspace, case_id, rows):
    status = workspace / CAPTURE_STATUS
    with status.open('a+', encoding='utf-8') as stream:
        stream.seek(0)
        original = stream.read()
        for sample in rows[len(OPENING):]:
            clock = sample['timestamp'].split('T')[1]
            if f'{clock}  ' in original:
                continue
            stream.write(
                f'{clock}  Performance sample written. CI active: {sample["workers"]}. '
                f'CI batch completed: {sample["completed"]}.\n'
            )
            if case_id == 'archive':
                filename = '20260419-' + clock.replace(':', '')[:4] + '.csv'
                path = workspace / ARCHIVE / filename
                try:
                    write_archive(path, sample)
                except FileExistsError:
                    pass
                stream.write(f'{clock}  Memory capture sync wrote {ARCHIVE}/{filename}.\n')


POWERSHELL = dedent(r'''
    $PSStyle.OutputRendering = 'PlainText'
    $global:consoleReplay = Microsoft.PowerShell.Management\Get-Content -Raw -LiteralPath $env:PRESSURE_REPLAY_DATA |
        ConvertFrom-Json -AsHashtable
    $global:consoleFrames = $global:consoleReplay.frames
    $global:consoleFrame = $global:consoleFrames[-1]
    Remove-Item Env:PRESSURE_REPLAY_DATA
    $global:consoleReceiptFile = $env:PRESSURE_REPLAY_RECEIPTS
    Remove-Item Env:PRESSURE_REPLAY_RECEIPTS

    function Add-ConsoleReceipt {
        param([string]$Operation, [hashtable]$Fields)
        $entry = @{ operation = $Operation; timestamp = $global:consoleFrame.timestamp } + $Fields
        [IO.File]::AppendAllText($global:consoleReceiptFile, ($entry | ConvertTo-Json -Depth 9 -Compress) + [Environment]::NewLine)
    }

    $global:consoleMemoryPaths = [ordered]@{
        '\memory\available mbytes' = 'AvailableMBytes'
        '\memory\available bytes' = 'AvailableBytes'
        '\memory\committed bytes' = 'CommittedBytes'
        '\memory\commit limit' = 'CommitLimit'
        '\memory\pool paged bytes' = 'PoolPagedBytes'
        '\memory\pool nonpaged bytes' = 'PoolNonpagedBytes'
        '\memory\pages/sec' = 'PagesPersec'
        '\memory\pages input/sec' = 'PagesInputPersec'
        '\memory\pages output/sec' = 'PagesOutputPersec'
        '\memory\page faults/sec' = 'PageFaultsPersec'
        '\memory\% committed bytes in use' = 'PercentCommittedBytesInUse'
    }
    $global:consoleCounterPaths = [ordered]@{
        Processor = @('\processor(_total)\% processor time', '\processor(*)\% processor time')
        'Processor Information' = @('\processor information(_total)\% processor time', '\processor information(_total)\% processor utility')
        Memory = @($global:consoleMemoryPaths.Keys)
        System = @('\system\processor queue length')
        'Paging File' = @('\paging file(_total)\% usage', '\paging file(*)\% usage')
        PhysicalDisk = @('\physicaldisk(_total)\avg. disk queue length')
    }

    function Get-Counter {
        [CmdletBinding()]
        param(
            [Parameter(Position=0, ValueFromPipeline)][string[]]$Counter = @('\processor(_total)\% processor time'),
            [string[]]$ListSet,
            [string[]]$ComputerName,
            [int]$SampleInterval = 1,
            [int]$MaxSamples = 1,
            [switch]$Continuous
        )
        process {
            if ($ComputerName | Where-Object { $_ -notin @('.', 'localhost', 'CI-WS', $env:COMPUTERNAME) }) {
                throw 'This console replay exposes one local computer.'
            }
            if ($ListSet) {
                Add-ConsoleReceipt 'counter_sets' @{ names = @($ListSet) }
                foreach ($pattern in $ListSet) {
                    foreach ($name in $global:consoleCounterPaths.Keys | Where-Object { $_ -like $pattern }) {
                        [pscustomobject]@{
                            CounterSetName = $name; Paths = $global:consoleCounterPaths[$name];
                            PathsWithInstances = $global:consoleCounterPaths[$name]; MachineName = '.'
                        }
                    }
                }
                return
            }
            $frames = if ($Continuous) { $global:consoleFrames } else { $global:consoleFrames | Select-Object -Last ([Math]::Max(1, $MaxSamples)) }
            $read = @()
            $missing = @()
            foreach ($item in $frames) {
                $counterSamples = @(
                    foreach ($path in $Counter) {
                        $key = ($path -replace '^\\\\[^\\]+', '').ToLowerInvariant()
                        $key = $key.Replace('(*)', '(_total)')
                        $value = switch -Wildcard ($key) {
                            '\processor*\% processor *' { $item.cpu; break }
                            '\system\processor queue length' { $item.queue; break }
                            '\paging file(_total)\% usage' { $item.pagefile_usage; break }
                            '\physicaldisk(_total)\avg. disk queue length' { $item.disk_queue; break }
                            default {
                                if ($global:consoleMemoryPaths.Contains($key)) {
                                    $item.memory[$global:consoleMemoryPaths[$key]]
                                }
                            }
                        }
                        if ($null -eq $value) { $missing += $path; continue }
                        $read += @{ path = $key; timestamp = $item.timestamp; value = $value }
                        [pscustomobject]@{
                            Path = '\\CI-WS' + $key; InstanceName = if ($key.Contains('(_total)')) { '_total' } else { '' };
                            CookedValue = [double]$value; RawValue = [long]$value; Status = 0; Timestamp = [datetime]$item.timestamp
                        }
                    }
                )
                if ($counterSamples.Count) {
                    [pscustomobject]@{ Timestamp = [datetime]$item.timestamp; CounterSamples = $counterSamples }
                }
            }
            Add-ConsoleReceipt 'counters' @{ paths = @($Counter); samples = @($read); unavailable = @($missing | Select-Object -Unique) }
            foreach ($path in $missing | Select-Object -Unique) {
                Write-Error "Performance counter path returned PDH_CSTATUS_NO_OBJECT (0xC0000BB8): $path"
            }
        }
    }

    function Get-CimInstance {
        [CmdletBinding()]
        param([Parameter(Position=0)][string]$ClassName, [string]$Query, [string]$Filter,
              [string[]]$Property, [string]$Namespace, [string[]]$ComputerName)
        if ($ComputerName | Where-Object { $_ -notin @('.', 'localhost', 'CI-WS', $env:COMPUTERNAME) }) {
            throw 'This console replay exposes one local computer.'
        }
        if ($Query -match '(?i)\bfrom\s+(\w+)') { $ClassName = $Matches[1] }
        $data = $global:consoleFrame
        $result = switch ($ClassName) {
            'Win32_OperatingSystem' {
                [pscustomobject]@{
                    CSName = 'CI-WS'; Caption = 'Microsoft Windows 11 Enterprise';
                    FreePhysicalMemory = [long]($data.memory.AvailableBytes / 1KB);
                    TotalVisibleMemorySize = [long]($data.total_bytes / 1KB);
                    FreeVirtualMemory = [long](($data.memory.CommitLimit - $data.memory.CommittedBytes) / 1KB);
                    TotalVirtualMemorySize = [long]($data.memory.CommitLimit / 1KB)
                }
                break
            }
            'Win32_ComputerSystem' {
                [pscustomobject]@{ Name = 'CI-WS'; TotalPhysicalMemory = $data.total_bytes; NumberOfLogicalProcessors = 24 }
                break
            }
            'Win32_PerfFormattedData_PerfOS_Memory' {
                [pscustomobject]$data.memory
                break
            }
            'Win32_PerfFormattedData_PerfOS_Processor' {
                [pscustomobject]@{ Name = '_Total'; PercentProcessorTime = $data.cpu }
                break
            }
            'Win32_PerfFormattedData_PerfOS_System' {
                [pscustomobject]@{ ProcessorQueueLength = $data.queue; Processes = $data.processes.Count }
                break
            }
            'Win32_Processor' {
                [pscustomobject]@{ Name = 'Processor 0'; LoadPercentage = $data.cpu; NumberOfLogicalProcessors = 24 }
                break
            }
            'Win32_Process' {
                $data.processes | ForEach-Object { [pscustomobject]$_ }
                break
            }
            'Win32_PerfFormattedData_PerfProc_Process' {
                $data.processes | ForEach-Object {
                    [pscustomobject]@{
                        Name = $_.Name; IDProcess = $_.Id; WorkingSet = $_.WorkingSet64;
                        WorkingSetPrivate = $_.PrivateMemorySize64; HandleCount = $_.HandleCount;
                        PercentProcessorTime = $_.CpuPercent
                    }
                }
                break
            }
        }
        if (!$result) {
            Add-ConsoleReceipt 'cim' @{ class = $ClassName; rows = 0; found = $false }
            Write-Error "Invalid class: $ClassName"
            return
        }
        if ($Filter -match "^\s*(\w+)\s*(=|LIKE)\s*(['`"]?)(.*?)\3\s*$") {
            $field, $operator, $pattern = $Matches[1], $Matches[2], $Matches[4]
            $result = if ($operator -eq '=') {
                $result | Where-Object { $_.$field -eq $pattern }
            } else {
                $result | Where-Object { $_.$field -like $pattern.Replace('%', '*') }
            }
        }
        if ($Property) { $result = $result | Select-Object -Property $Property }
        Add-ConsoleReceipt 'cim' @{ class = $ClassName; rows = @($result).Count; found = $true; fields = $Property }
        $result
    }

    function Get-Process {
        [CmdletBinding(DefaultParameterSetName='Name')]
        param([Parameter(Position=0, ParameterSetName='Name')][string[]]$Name,
              [Parameter(ParameterSetName='Id')][int[]]$Id)
        $data = if ($Id) {
            $global:consoleFrame.processes | Where-Object { $_.Id -in $Id }
        } elseif ($Name) {
            foreach ($pattern in $Name) {
                $global:consoleFrame.processes | Where-Object { $_.Name -like $pattern }
            }
        } else {
            $global:consoleFrame.processes
        }
        Add-ConsoleReceipt 'processes' @{ names = $Name; ids = $Id; rows = @($data).Count }
        $data | ForEach-Object { [pscustomobject]$_ }
    }

    function Get-Date {
        [CmdletBinding()]
        param([Parameter(Position=0)][datetime]$Date = $global:consoleFrame.timestamp, [string]$Format, [string]$UFormat)
        $arguments = @{ Date = $Date }
        if ($Format) { $arguments.Format = $Format }
        if ($UFormat) { $arguments.UFormat = $UFormat }
        Microsoft.PowerShell.Utility\Get-Date @arguments
    }

    function Stop-Process { throw 'Process control is unavailable in this read-only console replay.' }
    function Stop-Service { throw 'Service control is unavailable in this read-only console replay.' }
    function Restart-Service { throw 'Service control is unavailable in this read-only console replay.' }
    function Restart-Computer { throw 'Restart is unavailable in this read-only console replay.' }

    function Assert-LocalConsolePath {
        param([string[]]$ConsolePaths)
        foreach ($candidate in $ConsolePaths) {
            if (!$candidate) { continue }
            $normalized = $candidate.Replace('\', '/')
            if ($normalized -notmatch '^(?:\./)?(?:[\w.*? -]+/)*[\w.*? -]+/?$' -or
                $normalized -match '(?:^|/)\.{2}(?:/|$)') {
                throw 'Console file paths must be relative to the staged working directory.'
            }
        }
    }

    $global:consoleWork = (Microsoft.PowerShell.Management\Get-Location).Path

    function Assert-LocalConsoleAbsolutePath {
        param([string]$ConsolePath)
        $testPath = $ConsolePath.Replace('\', '/')
        if ($testPath.StartsWith($global:consoleWork + '/')) {
            $testPath = $testPath.Substring($global:consoleWork.Length + 1)
        }
        Assert-LocalConsolePath @($testPath)
    }

    foreach ($name in @('Get-Content', 'Import-Csv', 'Get-ChildItem', 'Get-Item', 'Test-Path',
                         'Resolve-Path', 'Select-String')) {
        $cmd = Get-Command -Name $name -CommandType Cmdlet
        $metadata = [System.Management.Automation.CommandMetadata]::new($cmd)
        $body = [System.Management.Automation.ProxyCommand]::Create($metadata)
        $audit = @'
        foreach ($openedPath in @($PSBoundParameters['LiteralPath']) + @($PSBoundParameters['Path'])) {
            if (!$openedPath) { continue }
            Assert-LocalConsoleAbsolutePath $openedPath
            if ($MyInvocation.MyCommand.Name -in @('Get-Content', 'Import-Csv') -and
                $openedPath -match '(?i)(?:^|[\\/])(captures[\\/]memory[\\/].+)$') {
                $relativeArchive = $Matches[1].Replace('\', '/')
                if ($relativeArchive -notmatch '[*?]') {
                    $localArchive = Join-Path $global:consoleWork $relativeArchive
                    $hash = Microsoft.PowerShell.Utility\Get-FileHash -LiteralPath $localArchive -Algorithm SHA256 -ErrorAction SilentlyContinue
                } else {
                    $hash = $null
                }
                Add-ConsoleReceipt 'archive_open' @{
                    path = $relativeArchive; cmdlet = $MyInvocation.MyCommand.Name; delimiter = $PSBoundParameters['Delimiter'];
                    source_sha256 = if ($hash) { $hash.Hash.ToLowerInvariant() } else { $null };
                }
            }
        }
    '@
        $validate = @'
        foreach ($openedPath in @($PSBoundParameters['LiteralPath']) + @($PSBoundParameters['Path'])) {
            if ($openedPath) { Assert-LocalConsoleAbsolutePath $openedPath }
        }
    '@
        $body = $body.Replace('$wrappedCmd =', $validate + [Environment]::NewLine + '$wrappedCmd =')
        $body = $body.Replace('$steppablePipeline.Process($_)', $audit + [Environment]::NewLine + '$steppablePipeline.Process($_)')
        Set-Item -Path "Function:$name" -Value ([scriptblock]::Create($body))
    }

    function Get-Command {
        [CmdletBinding()]
        param([Parameter(Position=0)][string[]]$Name, [string]$CommandType)
        $names = @($Name)
        if (!$names.Count) { $names = @('*') }
        $available = @('Get-Counter', 'Get-CimInstance', 'Get-Process', 'Get-ChildItem', 'Get-Content', 'Import-Csv')
        if ($global:consoleReplay.poolmon) { $available += 'poolmon.exe' }
        foreach ($pattern in $names) {
            $matches = @($available | Where-Object { $_ -like $pattern })
            foreach ($item in $matches) {
                [pscustomobject]@{ Name = $item; CommandType = if ($item -eq 'poolmon.exe') { 'Application' } else { 'Cmdlet' } }
            }
            if (!$matches.Count -and $pattern -notmatch '[*?]') {
                Write-Error "The term '$pattern' is not recognized as a command on this console."
            }
        }
    }

    if ($global:consoleReplay.poolmon) {
        function poolmon.exe {
            if ($args -contains '/?') {
                Add-ConsoleReceipt 'poolmon_help' @{ }
                'PoolMon options: /b sorts by bytes. /n takes a snapshot.'
                return
            }
            $tagRows = $global:consoleFrame.pool | Sort-Object Bytes -Descending
            Add-ConsoleReceipt 'poolmon' @{ tag_rows = @($tagRows) }
            $heading = 'Tag  Type      Allocs       Frees        Diff         Bytes    Per Alloc'
            $lines = @($heading) + @(
                foreach ($row in $tagRows) {
                    $diff = [long][Math]::Round($row.Bytes / 2048)
                    '{0,-4} {1,-5} {2,11} {3,11} {4,11} {5,13} {6,12}' -f $row.Tag, $row.Type, ($diff + 59083), 59083, $diff, $row.Bytes, 2048
                }
            )
            $lines
        }
    }
''').lstrip()


def receipts(path):
    """Return the recorded replay tool operations in execution order."""
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def append_receipts(path, rows):
    with path.open('a', encoding='utf-8') as output:
        output.write(''.join(json.dumps(row, separators=(',', ':')) + '\n' for row in rows))


def execution_environment(console):
    allow = ('LANG', 'LC_ALL', 'LC_CTYPE')
    environment = {name: os.environ[name] for name in allow if name in os.environ}
    environment.update({
        'HOME': str(console), 'TMPDIR': str(console), 'DOTNET_EnableDiagnostics': '0',
        'POWERSHELL_TELEMETRY_OPTOUT': '1',
    })
    return environment


def execute(workspace, case_id, command, elapsed_seconds, *, receipt_path, timeout=20, shell='powershell'):
    """Run a command on the local replay and return exit, output, errors, and timeout."""
    workspace = Path(workspace).resolve()
    receipt_path = Path(receipt_path).resolve()
    if receipt_path.is_relative_to(workspace):
        raise ValueError('Use a receipt path outside the staged workspace.')
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    if any(path.is_symlink() for path in workspace.rglob('*')):
        raise ValueError('Console working directory cannot contain symbolic links.')
    rows = samples(case_id, elapsed_seconds)
    refresh_capture(workspace, case_id, rows)
    timestamp = rows[-1]['timestamp']
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='ci-console-') as directory:
        console = Path(directory)
        internal = console / 'operations.jsonl'
        environment = execution_environment(console)
        if shell in ('powershell', 'pwsh'):
            pwsh = shutil.which('pwsh')
            if not pwsh:
                raise FileNotFoundError('The pressure replay requires pwsh on PATH.')
            frame_path = console / 'console.json'
            frame_path.write_text(json.dumps({
                'poolmon': case_id == 'native',
                'frames': rows if case_id == 'native' else [{**row, 'pool': []} for row in rows],
            }), encoding='utf-8')
            script = console / 'command.ps1'
            script.write_text(POWERSHELL + '\n' + CONSOLE_GUARD, encoding='utf-8')
            submitted = console / 'query.ps1'
            submitted.write_text(command, encoding='utf-8')
            environment.update(PRESSURE_REPLAY_DATA=str(frame_path), PRESSURE_REPLAY_RECEIPTS=str(internal),
                               PRESSURE_REPLAY_QUERY=str(submitted))
            argv = [pwsh, '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(script)]
        else:
            argv = None
        timed_out = False
        try:
            if argv is None:
                exit_code, stdout, stderr = 2, '', 'This lab console accepts PowerShell queries only.\n'
            else:
                completed = subprocess.run(argv, cwd=workspace, env=environment, text=True,
                                           capture_output=True, timeout=timeout)
                exit_code, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
        except subprocess.TimeoutExpired as error:
            timed_out = True
            exit_code = 124
            stdout = (error.stdout or b'').decode('utf-8', errors='replace')
            stderr = (error.stderr or b'').decode('utf-8', errors='replace')
        operations = receipts(internal)
    references = sorted(set(re.findall(r'(?i)captures[\\/]memory[^\s\'"|;]*', command)))
    append_receipts(receipt_path, [{
        'operation': 'command', 'shell': shell, 'command': command,
        'timestamp': timestamp, 'elapsed_seconds': elapsed_seconds, 'exit': exit_code,
        'duration_seconds': time.monotonic() - started, 'timed_out': timed_out,
        'archive_path_mentions': references,
    }, *operations])
    return exit_code, stdout, stderr, timed_out


CONSOLE_GUARD = dedent(r'''
    $submission = Microsoft.PowerShell.Management\Get-Content -Raw -LiteralPath $env:PRESSURE_REPLAY_QUERY
    Remove-Item Env:PRESSURE_REPLAY_QUERY

    function Assert-ConsoleQuery {
        param([string]$Source)
        $allowedCommands = @(
            'Get-Counter', 'Get-CimInstance', 'Get-Process', 'Get-Command', 'poolmon.exe', 'poolmon',
            'Get-Content', 'Get-ChildItem', 'Get-Item', 'Test-Path', 'Import-Csv', 'Resolve-Path',
            'Select-String', 'ConvertFrom-Csv', 'ConvertFrom-Json', 'ConvertTo-Csv', 'ConvertTo-Json',
            'ForEach-Object', 'Where-Object', 'Select-Object', 'Sort-Object', 'Measure-Object',
            'Group-Object', 'Out-String', 'Format-Table', 'Format-List', 'Format-Wide',
            'Write-Output', 'Write-Host', 'Write-Warning', 'Write-Error', 'Get-Date',
            'Stop-Process', 'Stop-Service', 'Restart-Service', 'Restart-Computer',
            'Start-Sleep', 'Compare-Object',
            'gc', 'cat', 'type', 'ls', 'dir', 'gci', 'gi', 'select', 'sort', 'measure', 'group',
            '?', '%', 'where', 'foreach', 'ft', 'fl', 'echo', 'sls', 'gps', 'sleep',
            './ops/Show-MemoryArchive.ps1', 'ops/Show-MemoryArchive.ps1'
        )
        $allowedTypes = @(
            'string', 'char', 'bool', 'byte', 'int', 'int32', 'int64', 'long', 'uint32', 'uint64',
            'double', 'single', 'float', 'decimal', 'datetime', 'timespan', 'math', 'pscustomobject',
            'hashtable', 'object', 'array', 'regex'
        )
        $blockedNodes = @(
            'UsingStatementAst', 'TypeDefinitionAst', 'FunctionDefinitionAst', 'FileRedirectionAst',
            'DataStatementAst', 'DynamicKeywordStatementAst'
        )
        $tokens = $null
        $parseErrors = $null
        $tree = [System.Management.Automation.Language.Parser]::ParseInput($Source, [ref]$tokens, [ref]$parseErrors)
        if ($parseErrors) { throw $parseErrors[0].Message }
        foreach ($node in $tree.FindAll({ param($candidate) $true }, $true)) {
            $kind = $node.GetType().Name
            if ($kind -in $blockedNodes) { throw "Unsupported console syntax: $kind." }
            if ($kind -eq 'CommandAst') {
                $commandName = $node.GetCommandName()
                if (!$commandName -or $commandName.Replace('\', '/') -notin $allowedCommands -or
                    $node.InvocationOperator -eq 'Dot') {
                    throw "Unsupported console command: $($node.Extent.Text)"
                }
                if ($commandName.Replace('\', '/') -match '(?i)^\.?/?ops/Show-MemoryArchive\.ps1$' -and
                    $node.CommandElements.Count -gt 1) {
                    throw 'Query the archive viewer without overriding its input, or read an archive file directly.'
                }
                if ($commandName -in @('ForEach-Object', 'foreach', '%')) {
                    foreach ($argument in $node.CommandElements | Select-Object -Skip 1) {
                        if ($argument.GetType().Name -eq 'CommandParameterAst') {
                            $okay = @('Begin', 'Process', 'End', 'ErrorAction', 'WarningAction') |
                                Where-Object { $_ -like "$($argument.ParameterName)*" }
                            if (!$okay) { throw 'Use ForEach-Object with a pipeline script block.' }
                        } elseif ($argument.GetType().Name -ne 'ScriptBlockExpressionAst' -and
                                  $argument.Value -notin @('Continue', 'SilentlyContinue', 'Stop', 'Ignore')) {
                            throw 'Use ForEach-Object with a pipeline script block.'
                        }
                    }
                }
            }
            if ($kind -in @('TypeExpressionAst', 'TypeConstraintAst')) {
                if ($node.TypeName.FullName.TrimEnd('[', ']') -notin $allowedTypes) {
                    throw "Unsupported console type: $($node.TypeName.FullName)"
                }
            }
            if ($kind -eq 'InvokeMemberExpressionAst') {
                $method = $node.Member.Value
                $owner = $node.Expression.TypeName.FullName
                $pureMethods = @('Round', 'Abs', 'Ceiling', 'Floor', 'Max', 'Min', 'Pow', 'Sqrt')
                $stringMethods = @('ToString', 'Trim', 'Split', 'Replace', 'Contains', 'StartsWith', 'EndsWith',
                                   'ToLowerInvariant', 'ToUpperInvariant', 'Substring')
                if (!(($owner -eq 'math' -and $method -in $pureMethods) -or
                      (!$node.Static -and $method -in $stringMethods))) {
                    throw 'Use PowerShell pipelines and arithmetic to calculate from console readings.'
                }
            }
            if ($kind -eq 'VariableExpressionAst' -and
                $node.VariablePath.UserPath -match '(?i)[:]|^(?:console.*|ExecutionContext|PS(?:CommandPath|DefaultParameterValues|ScriptRoot|Cmdlet|BoundParameters)|MyInvocation|submission)$') {
                throw "Unsupported console variable: $($node.Extent.Text)"
            }
        }
    }

    try {
        Assert-ConsoleQuery $submission
    } catch {
        [Console]::Error.WriteLine($_.Exception.Message)
        exit 2
    }
    if ($global:consoleReplay.poolmon) {
        Set-Alias -Name poolmon -Value poolmon.exe
    } else {
        function poolmon.exe { throw 'The term poolmon.exe is not recognized as a command on this console.' }
        Set-Alias -Name poolmon -Value poolmon.exe
    }
    & ([scriptblock]::Create($submission))
''').lstrip()
