[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$MacrArguments
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:MACR_ROOT = $(if ($env:MACR_ROOT) { $env:MACR_ROOT } else { $repoRoot })
$env:MACR_STATE_ROOT = $(
    if ($env:MACR_STATE_ROOT) { $env:MACR_STATE_ROOT } else { 'D:\AI_RESIDENCE\AI_Runtime\macr-state' }
)
$env:PYTHONPATH = Join-Path $repoRoot 'src'

$hadPythonUtf8 = Test-Path Env:PYTHONUTF8
$previousPythonUtf8 = $env:PYTHONUTF8
$hadPythonIoEncoding = Test-Path Env:PYTHONIOENCODING
$previousPythonIoEncoding = $env:PYTHONIOENCODING
$exitCode = 1
try {
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    python -X utf8 -m macr_runtime @MacrArguments
    $exitCode = $LASTEXITCODE
}
finally {
    if ($hadPythonUtf8) {
        $env:PYTHONUTF8 = $previousPythonUtf8
    }
    else {
        Remove-Item Env:PYTHONUTF8 -ErrorAction SilentlyContinue
    }
    if ($hadPythonIoEncoding) {
        $env:PYTHONIOENCODING = $previousPythonIoEncoding
    }
    else {
        Remove-Item Env:PYTHONIOENCODING -ErrorAction SilentlyContinue
    }
    $previousPythonUtf8 = $null
    $previousPythonIoEncoding = $null
}

exit $exitCode
