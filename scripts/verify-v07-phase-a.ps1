[CmdletBinding()]
param(
    [switch]$ManifestOnly
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$focusedModules = @(
    'tests.test_v07_contract_support',
    'tests.test_agent_contracts',
    'tests.test_semantic_contracts',
    'tests.test_observation_contracts',
    'tests.test_action_contracts',
    'tests.test_temporal_contracts',
    'tests.test_agent_contract_boundaries',
    'tests.test_v07_phase_a_manifest'
)

if ($ManifestOnly) {
    $manifest = [ordered]@{
        schema = 'macr-v07-phase-a-wrapper-manifest/v1'
        focused_modules = $focusedModules
        network_activity = $false
        provider_generation = $false
    }
    Write-Output ('PHASE_A_MANIFEST=' + ($manifest | ConvertTo-Json -Compress))
    exit 0
}

$env:MACR_ROOT = $repoRoot
if (-not $env:MACR_STATE_ROOT) {
    $env:MACR_STATE_ROOT = 'D:\AI_RESIDENCE\AI_Runtime\macr-state'
}
$env:MACR_TEST_TMP = Join-Path $env:MACR_STATE_ROOT 'test-tmp'
$env:PYTHONPATH = Join-Path $repoRoot 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'

$mutexName = 'Local\MACR_V07_PHASE_A_GATE'
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
        throw 'Timed out acquiring the MACR v0.7 Phase A verification mutex.'
    }

    $focusedOutput = python -m unittest @focusedModules -q 2>&1
    $focusedExit = $LASTEXITCODE
    if ($focusedExit) {
        $focusedOutput
        exit $focusedExit
    }
    $focusedText = $focusedOutput -join "`n"
    $focusedMatch = [regex]::Matches($focusedText, 'Ran\s+(\d+)\s+tests') |
        Select-Object -Last 1
    if (-not $focusedMatch) {
        throw 'Could not parse the focused Phase A test count.'
    }
    $focusedCount = [int]$focusedMatch.Groups[1].Value

    python -m compileall -q (Join-Path $repoRoot 'src') (Join-Path $repoRoot 'tests')
    if ($LASTEXITCODE) { exit $LASTEXITCODE }

    $inheritedOutput = & (Join-Path $PSScriptRoot 'verify.ps1') 2>&1
    $inheritedExit = $LASTEXITCODE
    if ($inheritedExit) {
        $inheritedOutput
        exit $inheritedExit
    }
    $inheritedText = $inheritedOutput -join "`n"
    $inheritedMatch = [regex]::Matches($inheritedText, 'Ran\s+(\d+)\s+tests') |
        Select-Object -Last 1
    if (-not $inheritedMatch) {
        throw 'Could not parse the inherited test count.'
    }
    $inheritedCount = [int]$inheritedMatch.Groups[1].Value

    $doctorText = python -m macr_runtime doctor --config (Join-Path $repoRoot 'config\providers.json')
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    $doctor = $doctorText | ConvertFrom-Json
    if ($doctor.network_activity -ne $false) {
        throw 'Offline doctor reported network activity.'
    }

    git -C $repoRoot diff --check
    if ($LASTEXITCODE) { exit $LASTEXITCODE }

    $status = @(git -C $repoRoot status --porcelain=v1 --untracked-files=normal)
    if ($status.Count -ne 0) {
        $status
        throw 'The Phase A verification subject must be a clean worktree.'
    }

    $gateManifest = Get-Content -LiteralPath (
        Join-Path $repoRoot 'tests\gates\v07_phase_a_contract_manifest.json'
    ) -Raw -Encoding UTF8 | ConvertFrom-Json
    $phaseBStarted = Test-Path -LiteralPath (
        Join-Path $repoRoot 'tests\gates\v07_phase_b_contract_manifest.json'
    )

    $summary = [ordered]@{
        schema = 'macr-v07-phase-a-summary/v1'
        candidate_commit = (git -C $repoRoot rev-parse HEAD)
        candidate_tree = (git -C $repoRoot rev-parse 'HEAD^{tree}')
        focused_tests = $focusedCount
        required_test_ids = @($gateManifest.required).Count
        inherited_tests = $inheritedCount
        schema_ids = @(
            'urn:evemisslab:macr:agent-contracts:v1',
            'urn:evemisslab:macr:semantic-contracts:v1',
            'urn:evemisslab:macr:observation-contracts:v1',
            'urn:evemisslab:macr:action-contracts:v1',
            'urn:evemisslab:macr:temporal-contracts:v1'
        )
        network_activity = $false
        provider_generation = $false
        git_clean = $true
        phase_b_started = [bool]$phaseBStarted
    }
    Write-Output ('PHASE_A_SUMMARY=' + ($summary | ConvertTo-Json -Compress -Depth 5))
}
finally {
    if ($mutexAcquired) {
        $verificationMutex.ReleaseMutex()
    }
    $verificationMutex.Dispose()
}
exit 0
