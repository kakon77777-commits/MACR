[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TaskPath,

    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$')]
    [string]$ProjectId = 'operator-default',

    [ValidateSet('interactive', 'routine', 'bulk')]
    [string]$AdmissionLane = 'routine'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$preflightOutput = & (Join-Path $PSScriptRoot 'macr.ps1') `
    glm-preflight `
    $TaskPath
$preflightExit = $LASTEXITCODE
if ($preflightExit -ne 0) {
    $preflightOutput | Write-Output
    exit $preflightExit
}
$preflightOutput = $null

$hadPrevious = Test-Path Env:ZAI_API_KEY
$previous = $env:ZAI_API_KEY
$exitCode = 1
try {
    Remove-Item Env:ZAI_API_KEY -ErrorAction SilentlyContinue
    & (Join-Path $PSScriptRoot 'macr.ps1') `
        invoke `
        glm_flash_worker `
        $TaskPath `
        --project-id $ProjectId `
        --admission-lane $AdmissionLane `
        --allow-network
    $exitCode = $LASTEXITCODE
}
finally {
    if ($hadPrevious) {
        $env:ZAI_API_KEY = $previous
    }
    else {
        Remove-Item Env:ZAI_API_KEY -ErrorAction SilentlyContinue
    }
    $previous = $null
}

exit $exitCode
