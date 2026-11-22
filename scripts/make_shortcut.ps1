# Generate desktop .lnk pointing to scripts/desktop_start.bat (WScript.Shell).
# Usage: pwsh -NoProfile -File scripts\make_shortcut.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot   # aesthetic-prism/
$bat = Join-Path $root "scripts\desktop_start.bat"
$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desktop "Aesthetic Prism.lnk"

$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut($lnkPath)
$lnk.TargetPath = $bat
$lnk.WorkingDirectory = $root
$lnk.WindowStyle = 7   # minimized
$lnk.Description = "Aesthetic Prism - start serve 0.0.0.0:8000 and open page"
$lnk.Save()

Write-Output "created: $lnkPath"
