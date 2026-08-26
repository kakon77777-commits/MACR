[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourcePath,
    [string]$TargetPath = 'D:\KEY\GOOGLE_VERTEX.json'
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:PYTHONPATH = Join-Path $repoRoot 'src'
$entryPoint = 'from macr_runtime.google_credentials import main; raise SystemExit(main())'
python -c $entryPoint --source $SourcePath --target $TargetPath
exit $LASTEXITCODE
