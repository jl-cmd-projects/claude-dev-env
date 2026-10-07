# Open a mod on the operator's desktop

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

## The auto mode safety check

The Remote Control session runs in auto mode, and its classifier reads the operator's message that
started the session. Two launches with the same commands went two ways:

| Seed message | Result |
| --- | --- |
| The operator asked to see the mod run: "can i see it in action? build the mod and show me" | The window opened. |
| The operator described a design change and asked for no run | The first step, writing the launcher script, was refused: `Permission for this action was denied by the Claude Code auto mode classifier. Reason: [Auto-Mode Bypass].` |

The likely rule, inferred from these two cases: start the session on the operator's own message that asks
to see or run the mod, and quote that ask in the instructions. When no such message exists, ask the
operator in one line whether to open the window, and start the session on the answer. A refused
step is final for that session; report the refusal text and stop.

## Steps

1. Start a Remote Control session, on the operator's message that asks to see the mod, in a folder on
   the operator's PC that is already approved.
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

5. Capture the window with [desktop-capture.md](desktop-capture.md) and check the PNG yourself.
6. Tell the operator the window is open and what to look at. Hand over a pasteable command only when
   the launch failed, and say why it failed.

## Verification

- The operator sees the window without any click.
- The window shows color and runs in Windows Terminal with PowerShell 7.
- The mod loads with no failure line, and its toast or pane appears.
