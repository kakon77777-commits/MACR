[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TaskPath
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
