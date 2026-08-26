[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourcePath,
    [string]$TargetPath = 'D:\KEY\GOOGLE_VERTEX.json'
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:PYTHONPATH = Join-Path $repoRoot 'src'
python -m macr_runtime.google_credentials --source $SourcePath --target $TargetPath
exit $LASTEXITCODE
