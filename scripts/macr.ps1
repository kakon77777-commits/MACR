[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$MacrArguments
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:MACR_ROOT = $(if ($env:MACR_ROOT) { $env:MACR_ROOT } else { $repoRoot })
$env:MACR_STATE_ROOT = $(
    if ($env:MACR_STATE_ROOT) { $env:MACR_STATE_ROOT } else { 'R:\AI_Runtime\macr-state' }
)
$env:PYTHONPATH = Join-Path $repoRoot 'src'

python -m macr_runtime @MacrArguments
exit $LASTEXITCODE
