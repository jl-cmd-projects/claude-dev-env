# Capture a desktop window

Run this on the operator's PC while the demo window is in front, after the mod fires. It copies the
pixels inside the window's rectangle, so a covered window, a minimized window, or a background tab
captures wrong. Open the demo with `wt.exe -w new` so its window is the one in front.

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

Report the path and size, and say whether the image shows color and the mod's output. The PNG stays on
the PC; a cloud session that needs to see it stages the file through the device folder tools, or has
the PC session post it.

A first run captured a 1752 x 936 PNG in color. It missed the toast because the demo had opened as a
tab behind the active one.
