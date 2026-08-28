[CmdletBinding()]
param(
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$stateRoot = 'D:\AI_RESIDENCE\AI_Runtime\macr-state'
$credentialHelper = 'D:\AI_RESIDENCE\AI_Runtime\codex-home\helpers\Get-XaiApiKey.ps1'
$pythonCommand = Get-Command python.exe -ErrorAction Stop

if (-not $repoRoot.StartsWith('D:\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'MACR Direct Chat source must be on D:.'
}
if (-not (Test-Path -LiteralPath $credentialHelper -PathType Leaf)) {
    throw 'The configured xAI credential helper is missing.'
}

if ($DryRun) {
    [pscustomobject]@{
        status = 'direct_chat_launch_dry_run'
        repo_root = $repoRoot
        state_root = $stateRoot
        credential_helper_present = $true
        python = $pythonCommand.Source
        hidden_child = $true
        network_activity = $false
    } | ConvertTo-Json -Compress
    exit 0
}

$xaiKey = $null
try {
    $xaiKey = (& $credentialHelper)
    if ([string]::IsNullOrWhiteSpace($xaiKey)) {
        throw 'The xAI credential helper returned no credential.'
    }
    $env:MACR_ROOT = $repoRoot
    $env:MACR_STATE_ROOT = $stateRoot
    $env:PYTHONPATH = Join-Path $repoRoot 'src'
    $env:XAI_API_KEY = $xaiKey

    $process = Start-Process `
        -FilePath $pythonCommand.Source `
        -ArgumentList @('-m', 'macr_runtime', 'direct-chat') `
        -WorkingDirectory $repoRoot `
        -WindowStyle Hidden `
        -PassThru

    [pscustomobject]@{
        status = 'direct_chat_launch_started'
        pid = $process.Id
        hidden_child = $true
    } | ConvertTo-Json -Compress
}
finally {
    Remove-Item Env:XAI_API_KEY -ErrorAction SilentlyContinue
    $xaiKey = $null
}
