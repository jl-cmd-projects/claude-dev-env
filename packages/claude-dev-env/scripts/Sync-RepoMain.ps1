#Requires -Version 7.0
<#
.SYNOPSIS
  Fast-forward a local main-tracking mirror to its remote main.

.DESCRIPTION
  Runs against any working tree that is meant to stay on one branch and follow
  a remote, such as a read-only mirror kept current by a scheduled task.

  Safety rules:
  - Only runs when the checked-out branch is the named branch, unless
    -Mirror is passed
  - Only runs when there are no tracked changes (untracked files are fine),
    unless -StashDirty is passed. A -Mirror return stashes the tree the old
    checkout left whatever -StashDirty says
  - Uses merge --ff-only (never force, never hard reset, never clean)
  - When the fast-forward fails because the files were already copied in,
    moves HEAD with a mixed reset, which writes no files. It keeps that move
    only when every file the remote changed now matches the remote
  - Logs and exits non-zero on skip, diverge, or failure so a Task Scheduler
    history row can surface a problem instead of a silent no-op

  Exit codes: 0 success, 1 git operation failed, 2 configuration or repo
  problem, 3 skipped by a safety rule, 4 diverged from the remote.

.PARAMETER RepoPath
  Absolute path to the git working tree. Required.

.PARAMETER Remote
  Remote name whose main is the source of truth (default: origin).

.PARAMETER Branch
  Local branch that must be checked out (default: main).

.PARAMETER StashDirty
  Changes the tracked-changes branch from skip to stash. With the switch, a
  tree carrying tracked modifications is stashed with the message
  "pre-sync stash <yyyy-MM-dd>: uncommitted other-stream edits before ff to
  <remote>/<branch>" right before the fast-forward, and the stash is left in
  the stash list for a human to inspect. Untracked files are never stashed.
  The stash runs only when the fast-forward is going to happen, so an
  already-up-to-date or diverged run creates no stash entry. If the
  fast-forward then fails, the stash is popped back so the edits do not go
  missing; when that pop also fails, the log names the stash entry so the
  operator can recover it by hand.

.PARAMETER Mirror
  Marks the tree as a mirror that must always sit on the named branch. With
  the switch, a checkout found on another branch or a detached HEAD is moved
  back: HEAD points at the local named branch again and a mixed reset moves
  the index there. Every path that still holds the old checkout's content,
  including files only the old checkout tracked, is stashed as "mirror
  return <yyyy-MM-dd>: tree of <checkout> at <tip>", which puts the named
  branch's files back. This stash runs with or without -StashDirty, because
  a mirror's tree belongs to the named branch. The log names the checkout
  and tip it left. A checkout with staged changes is skipped, so no staged
  content is lost. When a step of the return fails, HEAD and the index go
  back to the old checkout and the run exits 1. Without the switch, any
  other checkout is skipped.

.PARAMETER LogPath
  Absolute path to the run log (default: $HOME\.claude\logs\sync-repo-main.log).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$RepoPath,
    [string]$Remote = 'origin',
    [string]$Branch = 'main',
    [switch]$StashDirty,
    [switch]$Mirror,
    [string]$LogPath = (Join-Path $HOME '.claude\logs\sync-repo-main.log')
)

$ErrorActionPreference = 'Stop'

$logDirectory = Split-Path -Parent $LogPath
if (-not (Test-Path -LiteralPath $logDirectory)) {
    New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
}

function Write-SyncLog {
    param(
        [Parameter(Mandatory)]
        [string]$Level,
        [Parameter(Mandatory)]
        [string]$Message
    )
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'o'), $Level, $Message
    Add-Content -LiteralPath $LogPath -Value $line -Encoding utf8
    Write-Host $line
}

function Get-GitExecutable {
    $command = Get-Command git -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw 'git executable not found on PATH'
    }
    return $command.Source
}

function Invoke-Git {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )
    $output = & $script:gitPath -C $RepoPath @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output   = ($output | Out-String).Trim()
    }
}

function Get-GitDecoration {
    <#
      Reads a value used only to decorate a log line. The sync has already
      succeeded by the time these run, so a failure here returns a placeholder
      rather than turning a completed sync into a failed run.
    #>
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments,
        [Parameter(Mandatory)]
        [string]$Placeholder
    )
    $result = Invoke-Git -Arguments $Arguments
    if ($result.ExitCode -ne 0 -or -not $result.Output.Trim()) {
        return $Placeholder
    }
    return $result.Output
}

function Invoke-GitOrExit {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments,
        [Parameter(Mandatory)]
        [string]$FailureMessage,
        [Parameter(Mandatory)]
        [int]$FailureExitCode
    )
    $result = Invoke-Git -Arguments $Arguments
    if ($result.ExitCode -ne 0) {
        Write-SyncLog -Level 'ERROR' -Message "${FailureMessage}: $($result.Output)"
        exit $FailureExitCode
    }
    return $result.Output
}

function Invoke-MirrorReturn {
    <#
      Moves a mirror found on another branch or a detached HEAD back to the
      named branch. HEAD and the index move first, then every path where the
      tree still holds the old checkout's content is stashed, including files
      only the old checkout tracked. Any failure puts HEAD and the index back
      on the old checkout, so the next run meets the same state and tries again.
    #>
    param(
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string]$LeftBranch
    )
    $leftCheckoutName = if ($LeftBranch) { "branch '$LeftBranch'" } else { 'detached HEAD' }
    $stagedResult = Invoke-Git -Arguments @('diff', '--cached', '--quiet')
    if ($stagedResult.ExitCode -ne 0) {
        Write-SyncLog -Level 'SKIP' -Message "mirror return refused: $leftCheckoutName has staged changes"
        exit 3
    }
    $leftTip = Invoke-GitOrExit -Arguments @('rev-parse', 'HEAD') `
        -FailureMessage 'cannot read the tip of the checkout being left' -FailureExitCode 2
    $null = Invoke-GitOrExit -Arguments @('rev-parse', '--verify', '-q', "refs/heads/$Branch") `
        -FailureMessage "mirror has no local $Branch branch to return to" -FailureExitCode 2
    $leftOnlyResult = Invoke-Git -Arguments @('diff', '--name-only', '--no-renames', '-z', '--diff-filter=A', "refs/heads/$Branch", $leftTip)
    if ($leftOnlyResult.ExitCode -ne 0) {
        Write-SyncLog -Level 'ERROR' -Message "mirror return skipped: cannot list files only $leftCheckoutName tracks: $($leftOnlyResult.Output)"
        exit 1
    }
    $null = Invoke-GitOrExit -Arguments @('symbolic-ref', 'HEAD', "refs/heads/$Branch") `
        -FailureMessage "cannot point HEAD at $Branch" -FailureExitCode 1

    $resetResult = Invoke-Git -Arguments @('reset', '-q')
    $changedResult = if ($resetResult.ExitCode -eq 0) { Invoke-Git -Arguments @('diff', '--name-only', '--no-renames', '-z') } else { $resetResult }
    $failure = if ($resetResult.ExitCode -ne 0) { "mixed reset onto $Branch failed: $($resetResult.Output)" }
               elseif ($changedResult.ExitCode -ne 0) { "cannot list the tree left by $leftCheckoutName`: $($changedResult.Output)" }
    $leftTreeNote = 'the tree already matched'
    if (-not $failure) {
        $allLeftPaths = [System.Collections.Generic.List[string]]::new()
        foreach ($changedPath in Get-NulSeparatedPaths -Output $changedResult.Output) { $allLeftPaths.Add($changedPath) }
        foreach ($leftOnlyPath in Get-NulSeparatedPaths -Output $leftOnlyResult.Output) {
            if (Test-Path -LiteralPath (Join-Path $RepoPath $leftOnlyPath)) { $allLeftPaths.Add($leftOnlyPath) }
        }
        if ($allLeftPaths.Count -gt 0) {
            $leftTreeStashMessage = 'mirror return {0}: tree of {1} at {2}' -f (Get-Date -Format 'yyyy-MM-dd'), $leftCheckoutName, $leftTip
            $pathspecFile = New-TemporaryFile
            try {
                $pathspecText = (($allLeftPaths | Select-Object -Unique | ForEach-Object { ":(literal)$_" }) -join "`0") + "`0"
                [System.IO.File]::WriteAllText($pathspecFile.FullName, $pathspecText, [System.Text.UTF8Encoding]::new($false))
                $stashResult = Invoke-Git -Arguments @('stash', 'push', '--include-untracked', '-m', $leftTreeStashMessage, "--pathspec-from-file=$($pathspecFile.FullName)", '--pathspec-file-nul')
            }
            finally {
                Remove-Item -LiteralPath $pathspecFile.FullName -Force -ErrorAction SilentlyContinue
            }
            if ($stashResult.ExitCode -ne 0) {
                $failure = "stashing the tree of $leftCheckoutName failed: $($stashResult.Output)"
            }
            else {
                $leftTreeNote = "its tree is stashed as '$leftTreeStashMessage'"
            }
        }
    }
    if ($failure) {
        $restoreArguments = if ($LeftBranch) { @('symbolic-ref', 'HEAD', "refs/heads/$LeftBranch") } else { @('update-ref', '--no-deref', 'HEAD', $leftTip) }
        $restoreResult = Invoke-Git -Arguments $restoreArguments
        $indexResult = if ($resetResult.ExitCode -eq 0) { Invoke-Git -Arguments @('reset', '-q') } else { $restoreResult }
        $restoreNote = if ($restoreResult.ExitCode -eq 0 -and $indexResult.ExitCode -eq 0) { "HEAD and index are back on $leftCheckoutName at $leftTip" } else { "putting HEAD back on $leftCheckoutName at $leftTip also failed: $($restoreResult.Output) $($indexResult.Output)" }
        Write-SyncLog -Level 'ERROR' -Message "mirror return failed, $failure; $restoreNote"
        exit 1
    }
    Write-SyncLog -Level 'MIRROR' -Message "left $leftCheckoutName at $leftTip; HEAD is on $Branch and $leftTreeNote"
}

function Get-NulSeparatedPaths {
    param(
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string]$Output
    )
    return @($Output -split "`0" | Where-Object { $_ })
}

function Invoke-AdoptCopiedTree {
    <#
      Handles a mirror whose files are refreshed by copy while its HEAD stays
      behind. The fast-forward then refuses to overwrite the copied files,
      even though they already hold the remote content.

      A mixed reset moves HEAD and the index to the remote tip and writes no
      files. If any file the remote changed still differs afterwards, the
      reset goes back to the old tip, so the tree ends as it started.
    #>
    param(
        [Parameter(Mandatory)]
        [string]$LocalTip,
        [Parameter(Mandatory)]
        [string]$RemoteRef
    )
    $stagedResult = Invoke-Git -Arguments @('diff', '--cached', '--quiet')
    if ($stagedResult.ExitCode -ne 0) {
        Write-SyncLog -Level 'ERROR' -Message 'adopt skipped: the index holds staged changes'
        return $false
    }
    $changedResult = Invoke-Git -Arguments @('diff', '--name-only', '--no-renames', '-z', $LocalTip, $RemoteRef)
    if ($changedResult.ExitCode -ne 0) {
        Write-SyncLog -Level 'ERROR' -Message "adopt skipped: cannot list remote changes: $($changedResult.Output)"
        return $false
    }
    $allRemoteChangedPaths = [System.Collections.Generic.HashSet[string]]::new([string[]](Get-NulSeparatedPaths -Output $changedResult.Output))

    $resetResult = Invoke-Git -Arguments @('reset', '-q', $RemoteRef)
    if ($resetResult.ExitCode -ne 0) {
        Write-SyncLog -Level 'ERROR' -Message "adopt skipped: mixed reset failed: $($resetResult.Output)"
        return $false
    }
    $differResult = Invoke-Git -Arguments @('diff', '--name-only', '--no-renames', '-z')
    $allMismatchedPaths = @(Get-NulSeparatedPaths -Output $differResult.Output | Where-Object { $allRemoteChangedPaths.Contains($_) })
    if ($differResult.ExitCode -eq 0 -and $allMismatchedPaths.Count -eq 0) {
        return $true
    }

    $revertResult = Invoke-Git -Arguments @('reset', '-q', $LocalTip)
    if ($revertResult.ExitCode -ne 0) {
        Write-SyncLog -Level 'ERROR' -Message "adopt revert to $LocalTip failed; HEAD is at $RemoteRef with no file changed: $($revertResult.Output)"
        return $false
    }
    $shownPaths = ($allMismatchedPaths | Select-Object -First 20) -join '; '
    Write-SyncLog -Level 'ERROR' -Message "adopt refused: $($allMismatchedPaths.Count) file(s) the remote changed differ from it; HEAD kept at ${LocalTip}: $shownPaths"
    return $false
}

function Get-RunLockName {
    $lockPath = [System.IO.Path]::TrimEndingDirectorySeparator([System.IO.Path]::GetFullPath($RepoPath))
    $resolveLinkTarget = [System.IO.Directory].GetMethod('ResolveLinkTarget', [type[]]([string], [bool]))
    if ((Test-Path -LiteralPath $lockPath) -and ($null -ne $resolveLinkTarget)) {
        $finalTarget = [System.IO.Directory]::ResolveLinkTarget($lockPath, $true)
        if ($null -ne $finalTarget) {
            $lockPath = [System.IO.Path]::TrimEndingDirectorySeparator($finalTarget.FullName)
        }
    }
    $pathBytes = [System.Text.Encoding]::UTF8.GetBytes($lockPath.ToLowerInvariant())
    $pathHash = [System.Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData($pathBytes))
    return "Global\SyncRepoMain-$pathHash"
}

$runLock = [System.Threading.Mutex]::new($false, (Get-RunLockName))
try {
    $hasRunLock = $runLock.WaitOne(0)
}
catch [System.Threading.AbandonedMutexException] {
    $hasRunLock = $true
}
if (-not $hasRunLock) {
    Write-SyncLog -Level 'SKIP' -Message "another sync of $RepoPath is still running"
    exit 3
}

$env:GIT_TERMINAL_PROMPT = '0'
$env:GCM_INTERACTIVE = 'never'

try {
    if (-not (Test-Path -LiteralPath $RepoPath)) {
        Write-SyncLog -Level 'ERROR' -Message "repo path missing: $RepoPath"
        exit 2
    }

    $script:gitPath = Get-GitExecutable

    $currentBranch = Invoke-GitOrExit -Arguments @('branch', '--show-current') `
        -FailureMessage 'cannot read current branch' -FailureExitCode 2
    if ($currentBranch -ne $Branch) {
        if (-not $Mirror) {
            Write-SyncLog -Level 'SKIP' -Message "checkout is '$currentBranch', not '$Branch' (remote=$Remote)"
            exit 3
        }
        Invoke-MirrorReturn -LeftBranch $currentBranch
    }

    $statusOutput = Invoke-GitOrExit -Arguments @('status', '--porcelain') `
        -FailureMessage 'status failed' -FailureExitCode 2
    $trackedDirtyLines = @($statusOutput -split "`r?`n" | Where-Object { $_.Trim() -and -not $_.StartsWith('??') })
    if ($trackedDirtyLines.Count -gt 0 -and -not $StashDirty) {
        Write-SyncLog -Level 'SKIP' -Message ("tracked changes present; refusing sync: " + ($trackedDirtyLines -join '; '))
        exit 3
    }

    $null = Invoke-GitOrExit -Arguments @('-c', 'http.lowSpeedLimit=1000', '-c', 'http.lowSpeedTime=60', 'fetch', $Remote, $Branch) `
        -FailureMessage "fetch $Remote $Branch failed" -FailureExitCode 1

    $tipOutput = Invoke-GitOrExit -Arguments @('rev-parse', $Branch, "$Remote/$Branch") `
        -FailureMessage 'rev-parse of branch tips failed' -FailureExitCode 2
    $tipLines = @($tipOutput -split "`r?`n" | Where-Object { $_.Trim() })
    if ($tipLines.Count -ne 2) {
        Write-SyncLog -Level 'ERROR' -Message "rev-parse returned $($tipLines.Count) tip(s), expected 2: $tipOutput"
        exit 2
    }
    $localTip = $tipLines[0].Trim()
    $remoteTip = $tipLines[1].Trim()

    if ($localTip -eq $remoteTip) {
        $remoteUrl = Get-GitDecoration -Arguments @('remote', 'get-url', $Remote) -Placeholder '<url unavailable>'
        Write-SyncLog -Level 'OK' -Message "already up to date at $localTip ($Remote/$Branch $remoteUrl)"
        exit 0
    }

    $ancestorResult = Invoke-Git -Arguments @('merge-base', '--is-ancestor', $Branch, "$Remote/$Branch")
    if ($ancestorResult.ExitCode -ne 0) {
        $countResult = Invoke-Git -Arguments @('rev-list', '--left-right', '--count', "${Branch}...${Remote}/${Branch}")
        Write-SyncLog -Level 'ERROR' -Message "diverged from $Remote/$Branch (counts=$($countResult.Output)); fast-forward refused. local=$localTip remote=$remoteTip"
        exit 4
    }

    $didStash = $false
    if ($trackedDirtyLines.Count -gt 0) {
        $stashMessage = 'pre-sync stash {0}: uncommitted other-stream edits before ff to {1}/{2}' -f (Get-Date -Format 'yyyy-MM-dd'), $Remote, $Branch
        $stashResult = Invoke-Git -Arguments @('stash', 'push', '-m', $stashMessage)
        if ($stashResult.ExitCode -ne 0) {
            Write-SyncLog -Level 'ERROR' -Message "stash push failed; fast-forward abandoned: $($stashResult.Output)"
            exit 1
        }
        $didStash = $true
        Write-SyncLog -Level 'STASH' -Message ("stashed tracked changes as '" + $stashMessage + "' (left in stash list): " + ($trackedDirtyLines -join '; '))
    }

    $mergeResult = Invoke-Git -Arguments @('merge', '--ff-only', "$Remote/$Branch")
    if ($mergeResult.ExitCode -ne 0) {
        Write-SyncLog -Level 'ERROR' -Message "merge --ff-only failed: $($mergeResult.Output)"
        if ($didStash) {
            $popResult = Invoke-Git -Arguments @('stash', 'pop')
            if ($popResult.ExitCode -ne 0) {
                Write-SyncLog -Level 'ERROR' -Message ("stash pop failed after the failed fast-forward; the edits are still stashed as '" + $stashMessage + "' — recover them with git stash list and git stash pop: " + $popResult.Output)
                exit 1
            }
            Write-SyncLog -Level 'OK' -Message "restored the stashed edits to the working tree after the failed fast-forward"
        }
        if (-not (Invoke-AdoptCopiedTree -LocalTip $localTip -RemoteRef "$Remote/$Branch")) {
            exit 1
        }
        $subject = Get-GitDecoration -Arguments @('log', '-1', '--format=%h %s') -Placeholder '<subject unavailable>'
        Write-SyncLog -Level 'OK' -Message "$Branch $localTip -> $remoteTip adopted (files already matched) | $subject"
        exit 0
    }

    $subject = Get-GitDecoration -Arguments @('log', '-1', '--format=%h %s') -Placeholder '<subject unavailable>'
    $remoteUrl = Get-GitDecoration -Arguments @('remote', 'get-url', $Remote) -Placeholder '<url unavailable>'
    Write-SyncLog -Level 'OK' -Message "$Branch $localTip -> $remoteTip | $subject | $Remote/$Branch $remoteUrl"
    exit 0
}
catch {
    Write-SyncLog -Level 'ERROR' -Message $_.Exception.Message
    exit 1
}
