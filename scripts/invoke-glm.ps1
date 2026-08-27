[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TaskPath,

    [string]$KeyPath = 'D:\KEY\GLM.txt'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$absoluteKeyPath = [System.IO.Path]::GetFullPath($KeyPath)
$keyRoot = [System.IO.Path]::GetPathRoot($absoluteKeyPath)
if (-not [string]::Equals(
    $keyRoot,
    'D:\',
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw 'GLM key path must be on D:'
}
if (-not (Test-Path -LiteralPath $absoluteKeyPath -PathType Leaf)) {
    throw 'GLM key file does not exist'
}

$keyItem = Get-Item -LiteralPath $absoluteKeyPath -Force
if (($keyItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'GLM key file may not be a reparse point'
}
if ($keyItem.Length -le 0 -or $keyItem.Length -gt 16384) {
    throw 'GLM key file size is invalid'
}

$secret = [System.IO.File]::ReadAllText($absoluteKeyPath).Trim()
if ($secret -notmatch '^[^.\s]+\.[^.\s]+$') {
    throw 'GLM key shape is invalid'
}

$hadPrevious = Test-Path Env:ZAI_API_KEY
$previous = $env:ZAI_API_KEY
$exitCode = 1
try {
    $env:ZAI_API_KEY = $secret
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
    $secret = $null
    $previous = $null
}

exit $exitCode
