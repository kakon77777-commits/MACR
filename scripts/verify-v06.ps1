[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:MACR_ROOT = $repoRoot
if (-not $env:MACR_STATE_ROOT) {
    $env:MACR_STATE_ROOT = 'D:\AI_RESIDENCE\AI_Runtime\macr-state'
}
$env:MACR_TEST_TMP = Join-Path $env:MACR_STATE_ROOT 'test-tmp'
$env:PYTHONPATH = Join-Path $repoRoot 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'

$mutexName = 'Local\MACR_V06_QUIET_CENSUS'
$verificationMutex = [System.Threading.Mutex]::new($false, $mutexName)
$mutexAcquired = $false
try {
    try {
        $mutexAcquired = $verificationMutex.WaitOne(30000)
    }
    catch [System.Threading.AbandonedMutexException] {
        $mutexAcquired = $true
    }
    if (-not $mutexAcquired) {
        throw 'Timed out acquiring the MACR v0.6 verification mutex.'
    }
    $env:MACR_V06_QUIET_CENSUS_HELD = '1'

    & (Join-Path $PSScriptRoot 'Test-MacrQuietCensus.ps1') `
        -ConsecutiveZeroSamples 5 `
        -IntervalMilliseconds 250 `
        -SkipMutex | Out-Null
    if ($LASTEXITCODE) { exit $LASTEXITCODE }

    & (Join-Path $PSScriptRoot 'verify.ps1')
    if ($LASTEXITCODE) { exit $LASTEXITCODE }

$targetedModules = @(
    'tests.test_multiprocess_runtime',
    'tests.test_observatory_db',
    'tests.test_openrouter_discovery',
    'tests.test_planner',
    'tests.test_planning_contracts',
    'tests.test_model_identity',
    'tests.test_qualification',
    'tests.test_batch_authority',
    'tests.test_scheduler',
    'tests.test_t1_manifest',
    'tests.test_t1_dispatcher',
    'tests.test_token_policy',
    'tests.test_model_token_store',
    'tests.test_target_leases',
    'tests.test_coordinator_contract',
    'tests.test_crossfile_verifier',
    'tests.test_accounting',
    'tests.test_billing_port',
    'tests.test_differential',
    'tests.test_event_store'
)
python -m unittest @targetedModules -q
if ($LASTEXITCODE) { exit $LASTEXITCODE }

$doctorText = python -m macr_runtime doctor --config (Join-Path $repoRoot 'config\providers.json')
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$doctor = $doctorText | ConvertFrom-Json
if ($doctor.network_activity -ne $false) {
    throw 'Offline doctor reported network activity.'
}

git -C $repoRoot diff --check
if ($LASTEXITCODE) { exit $LASTEXITCODE }

$summaryText = python (Join-Path $repoRoot 'tests\helpers\v06_gate_summary.py')
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$summary = $summaryText | ConvertFrom-Json
if ($summary.network_activity -ne $false -or $summary.provider_generation -ne $false) {
    throw 'Offline gate summary reported provider activity.'
}
if ($summary.git_clean -ne $true) {
    throw 'The v0.6 offline checkpoint subject must be a clean Git worktree.'
}

& (Join-Path $PSScriptRoot 'Test-MacrQuietCensus.ps1') `
    -ConsecutiveZeroSamples 5 `
    -IntervalMilliseconds 250 `
    -SkipMutex | Out-Null
if ($LASTEXITCODE) { exit $LASTEXITCODE }

$compact = $summary | ConvertTo-Json -Compress -Depth 8
Write-Output ("V06_SUMMARY=" + $compact)
}
finally {
    Remove-Item Env:MACR_V06_QUIET_CENSUS_HELD -ErrorAction SilentlyContinue
    if ($mutexAcquired) {
        $verificationMutex.ReleaseMutex()
    }
    $verificationMutex.Dispose()
}
exit 0
