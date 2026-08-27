[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TaskPath,

    [string]$KeyPath = 'D:\KEY\GLM.txt',

    [string]$KeyRoot = 'D:\KEY'
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

$absoluteKeyRoot = [System.IO.Path]::GetFullPath($KeyRoot)
$rootDrive = [System.IO.Path]::GetPathRoot($absoluteKeyRoot)
if (-not [string]::Equals(
    $rootDrive,
    'D:\',
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw 'GLM key root must be on D:'
}
if (-not (Test-Path -LiteralPath $absoluteKeyRoot -PathType Container)) {
    throw 'GLM key root does not exist'
}
$currentRootComponent = $rootDrive
$rootRelative = $absoluteKeyRoot.Substring($rootDrive.Length).Trim('\')
if ($rootRelative) {
    foreach ($component in $rootRelative.Split('\')) {
        $currentRootComponent = Join-Path $currentRootComponent $component
        $rootComponentItem = Get-Item -LiteralPath $currentRootComponent -Force
        if (($rootComponentItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'GLM key-root ancestry may not contain a reparse point'
        }
    }
}
$rootItem = Get-Item -LiteralPath $absoluteKeyRoot -Force
if (($rootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'GLM key root may not be a reparse point'
}
$resolvedKeyRoot = (Resolve-Path -LiteralPath $absoluteKeyRoot).Path.TrimEnd('\')

$absoluteKeyPath = [System.IO.Path]::GetFullPath($KeyPath)
$keyDrive = [System.IO.Path]::GetPathRoot($absoluteKeyPath)
if (-not [string]::Equals(
    $keyDrive,
    'D:\',
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw 'GLM key path must be on D:'
}
if (-not (Test-Path -LiteralPath $absoluteKeyPath -PathType Leaf)) {
    throw 'GLM key file does not exist'
}
$resolvedKeyPath = (Resolve-Path -LiteralPath $absoluteKeyPath).Path
$requiredPrefix = $resolvedKeyRoot + '\'
if (-not $resolvedKeyPath.StartsWith(
    $requiredPrefix,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw 'GLM key file must remain beneath the canonical key root'
}

$relativeParent = [System.IO.Path]::GetDirectoryName(
    $resolvedKeyPath.Substring($requiredPrefix.Length)
)
$currentParent = $resolvedKeyRoot
if ($relativeParent) {
    foreach ($component in $relativeParent.Split('\')) {
        $currentParent = Join-Path $currentParent $component
        $componentItem = Get-Item -LiteralPath $currentParent -Force
        if (($componentItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'GLM key parent may not be a reparse point'
        }
    }
}

$keyItem = Get-Item -LiteralPath $resolvedKeyPath -Force
if (($keyItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'GLM key file may not be a reparse point'
}
if ($keyItem.Length -le 0 -or $keyItem.Length -gt 16384) {
    throw 'GLM key file size is invalid'
}

$secret = [System.IO.File]::ReadAllText($resolvedKeyPath).Trim()
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
