import { spawnSync } from 'node:child_process';

/** Env var that carries the folder path into the PowerShell probe, so no quoting reaches the command line. */
export const LOCKED_FOLDER_VARIABLE = 'CDE_LOCKED_FOLDER';
const LOCKER_PROBE_TIMEOUT_MILLISECONDS = 20000;
const LOCKED_FOLDER_PATTERN = /\b(EPERM|EBUSY|in use by another program|being used by another process)\b/i;
export const LOCKER_REASON_COMMAND_LINE = 'command-line';
export const LOCKER_REASON_OPEN_FILE = 'open-file';

/**
 * PowerShell that lists the processes holding a folder.
 *
 * Two checks run: a process whose command line or executable path names a
 * path inside the folder (an editor or shell opened on a file there), and a
 * process that holds a file in the folder open, from the Windows Restart
 * Manager. Each match prints one JSON line.
 */
export const LOCKER_PROBE_SCRIPT = String.raw`
$ErrorActionPreference = 'SilentlyContinue'
$folder = [IO.Path]::GetFullPath($env:${LOCKED_FOLDER_VARIABLE}).TrimEnd('\')
$forms = @($folder, $folder.Replace('\', '/'))
foreach ($process in Get-CimInstance Win32_Process) {
    $text = "$($process.CommandLine) $($process.ExecutablePath)"
    foreach ($form in $forms) {
        if ($text.IndexOf($form, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            [pscustomobject]@{ pid = [int]$process.ProcessId; name = $process.Name; reason = '${LOCKER_REASON_COMMAND_LINE}' } | ConvertTo-Json -Compress
            break
        }
    }
}
Add-Type -Namespace Cde -Name RestartManager -MemberDefinition @'
[StructLayout(LayoutKind.Sequential)] public struct UniqueProcess { public int ProcessId; public System.Runtime.InteropServices.ComTypes.FILETIME StartTime; }
[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] public struct ProcessInfo { public UniqueProcess Process; [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string AppName; [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)] public string ServiceName; public int ApplicationType; public uint AppStatus; public uint TSSessionId; [MarshalAs(UnmanagedType.Bool)] public bool Restartable; }
[DllImport("rstrtmgr.dll", CharSet = CharSet.Unicode)] public static extern int RmStartSession(out uint handle, int flags, System.Text.StringBuilder key);
[DllImport("rstrtmgr.dll", CharSet = CharSet.Unicode)] public static extern int RmRegisterResources(uint handle, uint fileCount, string[] files, uint appCount, IntPtr apps, uint serviceCount, string[] services);
[DllImport("rstrtmgr.dll")] public static extern int RmGetList(uint handle, out uint needed, ref uint count, [In, Out] ProcessInfo[] infos, ref uint reasons);
[DllImport("rstrtmgr.dll")] public static extern int RmEndSession(uint handle);
'@
$files = @(Get-ChildItem -LiteralPath $folder -Recurse -File -Force | Select-Object -First 2000 -ExpandProperty FullName)
if ($files.Count -gt 0) {
    $handle = [uint32]0
    if ([Cde.RestartManager]::RmStartSession([ref]$handle, 0, (New-Object Text.StringBuilder 64)) -eq 0) {
        try {
            if ([Cde.RestartManager]::RmRegisterResources($handle, [uint32]$files.Count, [string[]]$files, 0, [IntPtr]::Zero, 0, $null) -eq 0) {
                $needed = [uint32]0; $count = [uint32]64; $reasons = [uint32]0
                $infos = New-Object Cde.RestartManager+ProcessInfo[] 64
                if ([Cde.RestartManager]::RmGetList($handle, [ref]$needed, [ref]$count, $infos, [ref]$reasons) -eq 0) {
                    for ($index = 0; $index -lt $count; $index++) {
                        [pscustomobject]@{ pid = $infos[$index].Process.ProcessId; name = $infos[$index].AppName; reason = '${LOCKER_REASON_OPEN_FILE}' } | ConvertTo-Json -Compress
                    }
                }
            }
        } finally { [void][Cde.RestartManager]::RmEndSession($handle) }
    }
}
`;

/**
 * True when a host command's error text says a folder could not be replaced because it is in use.
 *
 * @param {string} errorText The command's error output.
 * @returns {boolean}
 */
export function namesALockedFolder(errorText) {
    return LOCKED_FOLDER_PATTERN.test(errorText ?? '');
}

/**
 * Parse the probe's JSON lines into one entry per process.
 *
 * @param {string} probeOutput Standard output of the PowerShell probe.
 * @param {number} ownProcessId This installer's process id, which never counts as a locker.
 * @returns {{pid: number, name: string, reason: string}[]}
 */
export function parseLockerLines(probeOutput, ownProcessId = process.pid) {
    const lockersByProcessId = new Map();
    for (const eachLine of (probeOutput ?? '').split(/\r?\n/)) {
        const trimmedLine = eachLine.trim();
        if (!trimmedLine.startsWith('{')) continue;
        let locker;
        try {
            locker = JSON.parse(trimmedLine);
        } catch {
            continue;
        }
        if (!Number.isInteger(locker.pid) || locker.pid === ownProcessId) continue;
        if (!lockersByProcessId.has(locker.pid)) lockersByProcessId.set(locker.pid, locker);
    }
    return [...lockersByProcessId.values()];
}

/**
 * List the running processes that hold a folder, on Windows.
 *
 * @param {string} folderPath The folder a host could not replace.
 * @param {object} [dependencies] Seams for tests.
 * @param {string} [dependencies.platform] The Node platform name.
 * @param {(folderPath: string) => string} [dependencies.runProbe] Returns the probe's standard output.
 * @returns {{pid: number, name: string, reason: string}[]} An empty list on other platforms or when the probe finds nothing.
 */
export function findFolderLockers(folderPath, dependencies = {}) {
    const platform = dependencies.platform ?? process.platform;
    if (platform !== 'win32' || !folderPath) return [];
    const runProbe = dependencies.runProbe ?? runLockerProbe;
    return parseLockerLines(runProbe(folderPath));
}

function runLockerProbe(folderPath) {
    const encodedScript = Buffer.from(LOCKER_PROBE_SCRIPT, 'utf16le').toString('base64');
    const probe = spawnSync('powershell', ['-NoProfile', '-NonInteractive', '-EncodedCommand', encodedScript], {
        encoding: 'utf8',
        env: { ...process.env, [LOCKED_FOLDER_VARIABLE]: folderPath },
        timeout: LOCKER_PROBE_TIMEOUT_MILLISECONDS,
        windowsHide: true,
    });
    return probe.stdout ?? '';
}

function describeLocker(locker) {
    const how = locker.reason === LOCKER_REASON_OPEN_FILE
        ? 'has a file in it open'
        : 'was started on a path inside it';
    return `${locker.name} (PID ${locker.pid}, ${how})`;
}

/**
 * Tell the user exactly what to close so a locked plugin folder can be replaced.
 *
 * @param {string} folderPath The folder the host could not replace.
 * @param {{pid: number, name: string, reason: string}[]} allLockers What holds it.
 * @returns {string}
 */
export function lockedFolderAdvice(folderPath, allLockers) {
    if (allLockers.length === 0) {
        return `No running process names ${folderPath} or holds a file in it open, so a window or terminal`
            + ' whose working folder is inside it is the likely holder. Close it and run the install again.';
    }
    const verb = allLockers.length === 1 ? 'holds' : 'hold';
    return `Close ${allLockers.map(describeLocker).join(', ')}, which ${verb} ${folderPath}, and run the install again.`;
}
