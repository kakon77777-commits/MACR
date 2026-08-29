[CmdletBinding()]
param(
    [switch]$DryRun,
    [string]$CredentialPath = 'D:\KEY\GROK.txt'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$stateRoot = 'D:\AI_RESIDENCE\AI_Runtime\macr-state'
$credentialHelper = (Resolve-Path (Join-Path $PSScriptRoot 'read-grok-key.ps1')).Path
$pythonCommand = Get-Command python.exe -ErrorAction Stop

if (-not $repoRoot.StartsWith('D:\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'MACR Direct Chat source must be on D:.'
}
if (-not (Test-Path -LiteralPath $credentialHelper -PathType Leaf)) {
    throw 'The configured xAI credential helper is missing.'
}

$xaiKey = $null
$credentialUsable = $false
try {
    $xaiKey = (& $credentialHelper -CredentialPath $CredentialPath)
    $credentialUsable = -not [string]::IsNullOrWhiteSpace($xaiKey)
}
catch {
    $xaiKey = $null
    $credentialUsable = $false
}

if ($DryRun) {
    [pscustomobject]@{
        status = 'direct_chat_launch_dry_run'
        repo_root = $repoRoot
        state_root = $stateRoot
        credential_helper_present = $true
        python = $pythonCommand.Source
        hidden_child = $true
        grok_credential_usable = $credentialUsable
        direct_service_would_start = $true
        network_activity = $false
    } | ConvertTo-Json -Compress
    $xaiKey = $null
    exit 0
}

try {
    $env:MACR_ROOT = $repoRoot
    $env:MACR_STATE_ROOT = $stateRoot
    $env:PYTHONPATH = Join-Path $repoRoot 'src'
    if ($credentialUsable) {
        $env:XAI_API_KEY = $xaiKey
    }
    else {
        Remove-Item Env:XAI_API_KEY -ErrorAction SilentlyContinue
    }

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
