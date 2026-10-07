---
name: run-mod-on-desktop
description: >-
  Open a visible, colored Claude Code window on the operator's Windows desktop with a mod (plugin) loaded through --plugin-dir, from a Remote Control session, with no operator step. Optionally capture that window to a PNG as proof. Use when a mod, toast, pane or status line must be shown or checked on the operator's own screen.
---

# Run a mod on the desktop

## Principle

A toast, pane or status line shows only in the Claude Code window that loads the mod. A Remote Control
session has no window the operator can see. So the session opens a new desktop window that loads the
mod, and the operator only looks at it.

## Gotchas

- A mod loaded inside the Remote Control session fires its toast there. The operator sees nothing.
- `/plugin install` plus hot reload asks the operator to click "Enable for this session". `--plugin-dir` on a new window skips that prompt.
- A child window inherits `NO_COLOR=1` and `CLAUDE_CODE_CHILD_SESSION=1` from the Remote Control process. The window then runs black and white. Remove both variables in the child before `claude` starts.
- `Start-Process pwsh` opens the old console host. Launch through `wt.exe` to get Windows Terminal.
- `wt.exe new-tab` lands in an existing Windows Terminal window. A screen capture then shows whichever tab is active. Use `wt.exe -w new` for a window of its own.
- `wt.exe` is an app execution alias. Call it by its full path under `%LOCALAPPDATA%\Microsoft\WindowsApps`.
- A screen capture copies pixels on screen. A covered or minimized window captures wrong.

## Process

1. Start a Remote Control session in a folder on the operator's PC that is already approved.
2. Clone the mod's branch to a fresh temporary folder:

   ```powershell
   $dir = Join-Path $env:TEMP ('mod-demo-' + (Get-Date -Format 'HHmmss'))
   git clone -q --depth 1 -b <branch> <repo-url> $dir
   ```

3. Write a launcher script that clears the inherited variables and starts Claude Code with the mod:

   ```powershell
   $script = Join-Path $env:TEMP 'mod-demo.ps1'
   @"
   Remove-Item env:NO_COLOR, env:CLAUDE_CODE_CHILD_SESSION -ErrorAction SilentlyContinue
   Set-Location `$env:USERPROFILE
   claude --plugin-dir '$dir\plugins\<mod>' '<one harmless prompt that fires the mod>'
   "@ | Set-Content -Encoding utf8 $script
   ```

4. Open it in its own Windows Terminal window with PowerShell 7:

   ```powershell
   $wt = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\wt.exe'
   Start-Process $wt -ArgumentList "-w new new-tab --title `"Mod demo`" pwsh -NoExit -File `"$script`""
   ```

5. Tell the operator the window is open and what to look at. Hand over a pasteable command only when the launch failed, and say why it failed.

## Capture the window

Run this while the demo window is in front, after the mod fires:

```powershell
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type @"
using System; using System.Runtime.InteropServices;
public struct RECT { public int Left, Top, Right, Bottom; }
public static class W { [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r); }
"@
$window = Get-Process WindowsTerminal | Where-Object MainWindowTitle | Select-Object -First 1
$rect = New-Object RECT
[W]::GetWindowRect($window.MainWindowHandle, [ref]$rect) | Out-Null
$size = New-Object System.Drawing.Size(($rect.Right - $rect.Left), ($rect.Bottom - $rect.Top))
$bitmap = New-Object System.Drawing.Bitmap $size.Width, $size.Height
[System.Drawing.Graphics]::FromImage($bitmap).CopyFromScreen($rect.Left, $rect.Top, 0, 0, $size)
$bitmap.Save((Join-Path $env:TEMP 'mod-demo.png'))
```

Report the path and size, and say whether the image shows color and the mod's output.

## Verification

- The operator sees the window without any click.
- The window shows color and runs in Windows Terminal with PowerShell 7.
- The mod loads with no failure line, and its toast or pane appears.
