[CmdletBinding()]
param(
    [string]$CredentialPath = 'D:\KEY\GROK.txt'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($CredentialPath)) {
    throw 'The configured Grok credential path is missing.'
}
$candidate = [System.IO.Path]::GetFullPath($CredentialPath)
if (-not $candidate.StartsWith('D:\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'The configured Grok credential must be on D:.'
}
if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
    throw 'The configured Grok credential file is missing.'
}

$keyFile = Get-Item -LiteralPath $candidate
if (($keyFile.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'The configured Grok credential file may not be a reparse point.'
}
if ($keyFile.Length -lt 20 -or $keyFile.Length -gt 4096) {
    throw 'The configured Grok credential file has an invalid size.'
}

$raw = [System.IO.File]::ReadAllText($candidate, [System.Text.Encoding]::UTF8)
$token = $raw.Trim()
if ($token.Length -lt 20 -or $token.Length -gt 4096 -or $token -match '\s') {
    throw 'The configured Grok credential has an invalid shape.'
}

$legacyShape = $token -match '\Axai-[A-Za-z0-9_-]{20,}\z'
$uuidShape = $token -match '\A[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\z'
if (-not ($legacyShape -or $uuidShape)) {
    throw 'The configured Grok credential has an unsupported format.'
}

# Emit one success-pipeline value so an in-process PowerShell launcher can
# capture it without diagnostic output.
$token
