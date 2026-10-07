# Capture a desktop window

Run this on the operator's PC after the mod fires. It asks the window to paint itself into a bitmap
with `PrintWindow`, so another window on top does not spoil the image. Open the demo with
`wt.exe -w new` and `--suppressApplicationTitle`, so its window keeps the demo title and the block
below can find it by that title.

```powershell
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public struct RECT { public int Left, Top, Right, Bottom; }
public static class W {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
}
"@
[W]::SetProcessDPIAware() | Out-Null
$window = Get-Process WindowsTerminal | Where-Object MainWindowTitle -like '*Mod demo*' | Select-Object -First 1
$rect = New-Object RECT
[W]::GetWindowRect($window.MainWindowHandle, [ref]$rect) | Out-Null
$bitmap = New-Object System.Drawing.Bitmap ($rect.Right - $rect.Left), ($rect.Bottom - $rect.Top)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$hdc = $graphics.GetHdc()
[W]::PrintWindow($window.MainWindowHandle, $hdc, 2) | Out-Null
$graphics.ReleaseHdc($hdc)
$bitmap.Save((Join-Path $env:TEMP 'mod-demo.png'))
```

Report the path and size, and say whether the image shows color and the mod's output. The PNG stays on
the PC; a cloud session that needs to see it stages the file through the device folder tools, or has
the PC session post it. A toast fades, so capture while it shows, or capture twice.

## What went wrong before

| Capture | Result |
| --- | --- |
| `CopyFromScreen` on the window rectangle, demo opened with `new-tab` | 1752 x 936 in color, but it showed the active tab and missed the toast. |
| `CopyFromScreen` without `SetProcessDPIAware` | The image held the wrong region, with other windows in it. |
| `SetProcessDPIAware`, then `PrintWindow` with flag 2 (`PW_RENDERFULLCONTENT`) | 2520 x 936 in full color, as reported by the PC session. |
