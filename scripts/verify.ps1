[CmdletBinding()]
param()

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $env:MACR_ROOT) {
    $env:MACR_ROOT = $repoRoot
}
if (-not $env:MACR_STATE_ROOT) {
    $env:MACR_STATE_ROOT = 'D:\AI_RESIDENCE\AI_Runtime\macr-state'
}
if (-not $env:CODEX_HOME_TARGET) {
    $env:CODEX_HOME_TARGET = 'D:\AI_RESIDENCE\AI_Runtime\codex-home'
}
$env:MACR_TEST_TMP = Join-Path $env:MACR_STATE_ROOT 'test-tmp'
$env:PYTHONPATH = Join-Path $repoRoot 'src'

& (Join-Path $PSScriptRoot 'init-state.ps1') -StateRoot $env:MACR_STATE_ROOT | Out-Null
if ($LASTEXITCODE) { exit $LASTEXITCODE }

python -m unittest discover -s (Join-Path $repoRoot 'tests') -t $repoRoot -v
if ($LASTEXITCODE) { exit $LASTEXITCODE }

python -m compileall -q (Join-Path $repoRoot 'src') (Join-Path $repoRoot 'tests')
if ($LASTEXITCODE) { exit $LASTEXITCODE }

$operationalTargets = @(
    (Join-Path $repoRoot 'src'),
    (Join-Path $repoRoot 'config'),
    (Join-Path $repoRoot 'examples'),
    (Join-Path $repoRoot '.env.example'),
    (Join-Path $repoRoot 'scripts\macr.ps1'),
    (Join-Path $repoRoot 'scripts\init-state.ps1')
)
$operationalPathMatches = rg -n -S -e '[CR]:[\\/]' -- $operationalTargets
if ($LASTEXITCODE -eq 0 -and $operationalPathMatches) {
    $operationalPathMatches
    throw 'Operational C: or historical R: path detected.'
}
if ($LASTEXITCODE -notin @(0, 1)) { exit $LASTEXITCODE }

$secretMatches = rg -n --hidden --no-ignore `
    -g '!**/.git/**' `
    -g '!**/.worktrees/**' `
    -g '!**/.venv/**' `
    -g '!**/__pycache__/**' `
    -g '!**/*.pyc' `
    -e '(?:^|[^A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}' `
    -e '(?:^|[^A-Za-z0-9])xai-[A-Za-z0-9_-]{20,}' `
    -e 'Bearer [A-Za-z0-9_-]{20,}' `
    -e '-----BEGIN (?:RSA )?PRIVATE KEY-----' `
    -e '(?i)\x22private_key\x22\s*:\s*\x22[^\x22]{16,}' `
    -e '(?i)(?:api[_-]?key|access[_-]?token|secret)\s*[=:]\s*[\x22\x27]?[A-Za-z0-9_./+=-]{16,}' `
    -- $repoRoot
if ($LASTEXITCODE -eq 0 -and $secretMatches) {
    $secretMatches
    throw 'Potential committed secret material detected.'
}
if ($LASTEXITCODE -notin @(0, 1)) { exit $LASTEXITCODE }

if (Test-Path (Join-Path $repoRoot '.git')) {
    git -C $repoRoot diff --check
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
}

python -m macr_runtime doctor --config (Join-Path $repoRoot 'config\providers.json')
exit $LASTEXITCODE
