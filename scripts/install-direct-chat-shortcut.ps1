[CmdletBinding()]
param(
    [string]$ShortcutPath,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcherPath = (Resolve-Path (Join-Path $PSScriptRoot 'start-direct-chat.ps1')).Path
$powershellPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

if ([string]::IsNullOrWhiteSpace($ShortcutPath)) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $ShortcutPath = Join-Path $desktop 'MACR Direct Chat (Alpha).lnk'
}
$shortcutFullPath = [System.IO.Path]::GetFullPath($ShortcutPath)

if (-not $launcherPath.StartsWith('D:\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'The Direct Chat launcher must be on D:.'
}
if (-not (Test-Path -LiteralPath $powershellPath -PathType Leaf)) {
    throw 'Windows PowerShell executable is missing.'
}

$arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $launcherPath + '"'
$report = [ordered]@{
    status = $(if ($DryRun) { 'shortcut_dry_run' } else { 'shortcut_created' })
    shortcut_path = $shortcutFullPath
    target = $powershellPath
    arguments = $arguments
    working_directory = $repoRoot
    created = (-not $DryRun)
}

if (-not $DryRun) {
    $parent = Split-Path -Parent $shortcutFullPath
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        throw 'Shortcut parent directory does not exist.'
    }
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutFullPath)
    $shortcut.TargetPath = $powershellPath
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $repoRoot
    $shortcut.Description = 'MACR 0.5.0a4 Direct Chat UI 0.1 alpha'
    $shortcut.IconLocation = $powershellPath + ',0'
    $shortcut.Save()
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shortcut)
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

[pscustomobject]$report | ConvertTo-Json -Compress
