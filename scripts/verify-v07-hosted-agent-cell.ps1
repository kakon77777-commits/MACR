[CmdletBinding()]
param(
    [switch]$ManifestOnly
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$focusedModules = @(
    'tests.test_hosted_agent_cell_contracts',
    'tests.test_hosted_agent_cell_blobs_tools',
    'tests.test_hosted_agent_cell_runner',
    'tests.test_hosted_agent_cell_model_port',
    'tests.test_provider_admission',
    'tests.test_provider_admission_runtime',
    'tests.test_t1_dispatcher',
    'tests.test_cli',
    'tests.test_storage',
    'tests.test_v07_hosted_agent_cell_gate'
)

if ($ManifestOnly) {
    $manifest = [ordered]@{
        schema = 'macr-v07-hosted-agent-cell-wrapper-manifest/v1'
        focused_modules = $focusedModules
        contract_manifest = 'tests/gates/v07_hosted_agent_cell_contract_manifest.json'
        inherited_gate = 'scripts/verify-v07-phase-c.ps1'
        network_activity = $false
        provider_generation = $false
        shared_state_migration = $false
        shared_policy_activation = $false
        canonical_v070a1_closed = $false
    }
    Write-Output ('HOSTED_AGENT_CELL_MANIFEST=' + (
        $manifest | ConvertTo-Json -Compress
    ))
    exit 0
}

$env:MACR_ROOT = $repoRoot
if (-not $env:MACR_STATE_ROOT) {
    $env:MACR_STATE_ROOT = 'D:\AI_RESIDENCE\AI_Runtime\macr-state'
}
$env:MACR_TEST_TMP = Join-Path $env:MACR_STATE_ROOT 'test-tmp'
$env:PYTHONPATH = Join-Path $repoRoot 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

$mutex = [System.Threading.Mutex]::new(
    $false,
    'Local\MACR_V07_HOSTED_AGENT_CELL_GATE'
)
$acquired = $false
try {
    try {
        $acquired = $mutex.WaitOne(30000)
    }
    catch [System.Threading.AbandonedMutexException] {
        $acquired = $true
    }
    if (-not $acquired) {
        throw 'Timed out acquiring the hosted Agent Cell verification mutex.'
    }

    $runner = Join-Path $repoRoot 'tests\helpers\unittest_json.py'
    $focusedOutput = @(python $runner @focusedModules)
    if ($LASTEXITCODE) {
        $focusedOutput
        exit $LASTEXITCODE
    }
    $focusedLine = $focusedOutput |
        Where-Object { $_.ToString().StartsWith('UNITTEST_SUMMARY=') } |
        Select-Object -Last 1
    if (-not $focusedLine) {
        throw 'Hosted Agent Cell focused tests emitted no summary.'
    }
    $focused = $focusedLine.ToString().Substring(
        'UNITTEST_SUMMARY='.Length
    ) | ConvertFrom-Json
    if ($focused.successful -ne $true) {
        $focusedOutput
        throw 'Hosted Agent Cell focused tests did not report success.'
    }

    python -m compileall -q (Join-Path $repoRoot 'src') (
        Join-Path $repoRoot 'tests'
    )
    if ($LASTEXITCODE) { exit $LASTEXITCODE }

    $phaseCOutput = @(& (
        Join-Path $PSScriptRoot 'verify-v07-phase-c.ps1'
    ) 2>&1)
    $phaseCExit = $LASTEXITCODE
    if ($phaseCExit) {
        $phaseCOutput
        exit $phaseCExit
    }
    $phaseCLine = $phaseCOutput |
        Where-Object { $_.ToString().StartsWith('PHASE_C_SUMMARY=') } |
        Select-Object -Last 1
    if (-not $phaseCLine) {
        throw 'Inherited Phase C gate emitted no summary.'
    }
    $phaseC = $phaseCLine.ToString().Substring(
        'PHASE_C_SUMMARY='.Length
    ) | ConvertFrom-Json
    if ($phaseC.network_activity -ne $false -or
        $phaseC.provider_generation -ne $false) {
        throw 'Inherited Phase C gate violated the offline boundary.'
    }

    git -C $repoRoot diff --check
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    $status = @(git -C $repoRoot status --porcelain=v1 --untracked-files=normal)
    if ($status.Count -ne 0) {
        $status
        throw 'Hosted Agent Cell verification requires a clean worktree.'
    }

    $contract = Get-Content -LiteralPath (
        Join-Path $repoRoot 'tests\gates\v07_hosted_agent_cell_contract_manifest.json'
    ) -Raw -Encoding UTF8 | ConvertFrom-Json
    $summary = [ordered]@{
        schema = 'macr-v07-hosted-agent-cell-summary/v1'
        candidate_commit = (git -C $repoRoot rev-parse HEAD)
        candidate_tree = (git -C $repoRoot rev-parse 'HEAD^{tree}')
        focused_tests = [int]$focused.tests_run
        required_test_ids = @($contract.required).Count
        inherited_tests = [int]$phaseC.inherited_tests
        phase_c_focused_tests = [int]$phaseC.focused_tests
        real_adapter_fake_transport_providers = @('grok', 'glm_flash_worker')
        latest_builtin_provider_policy_revisions = [ordered]@{
            glm_flash_worker = 3
            grok = 2
        }
        network_activity = $false
        provider_generation = $false
        shared_state_migration = $false
        shared_policy_activation = $false
        canonical_v070a1_closed = $false
        git_clean = $true
    }
    Write-Output ('HOSTED_AGENT_CELL_SUMMARY=' + (
        $summary | ConvertTo-Json -Compress -Depth 6
    ))
}
finally {
    if ($acquired) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
exit 0
