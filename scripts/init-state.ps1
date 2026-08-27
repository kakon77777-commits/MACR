[CmdletBinding()]
param(
    [string]$StateRoot = $(if ($env:MACR_STATE_ROOT) { $env:MACR_STATE_ROOT } else { 'D:\AI_RESIDENCE\AI_Runtime\macr-state' })
)

$resolvedDrive = [System.IO.Path]::GetPathRoot($StateRoot)
if ($resolvedDrive -ne 'D:\') {
    throw "Persistent MACR state is allowed only on D:. Refusing: $StateRoot"
}

$paths = @(
    'ledger',
    'artifacts',
    'cache',
    'test-tmp',
    'runtime',
    'accounting',
    'candidates',
    'quarantine',
    'direct',
    'settings'
) | ForEach-Object {
    Join-Path -Path $StateRoot -ChildPath $_
}

foreach ($path in $paths) {
    New-Item -ItemType Directory -Force -Path $path | Out-Null
}

$paths
