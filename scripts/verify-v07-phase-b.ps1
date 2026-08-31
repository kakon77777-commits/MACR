[CmdletBinding()]
param(
    [switch]$ManifestOnly
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$focusedModules = @(
    'tests.test_agent_state',
    'tests.test_agent_lifecycle',
    'tests.test_agent_database',
    'tests.test_agent_events',
    'tests.test_agent_store',
    'tests.test_agent_service',
    'tests.test_agent_ownership',
    'tests.test_agent_rebuild',
    'tests.test_agent_multiprocess',
    'tests.test_v07_phase_b_manifest'
)
$phaseCManifestPath = Join-Path $repoRoot (
    'tests\gates\v07_phase_c_contract_manifest.json'
)
$phaseCStarted = Test-Path -LiteralPath $phaseCManifestPath

if ($ManifestOnly) {
    $manifest = [ordered]@{
        schema = 'macr-v07-phase-b-wrapper-manifest/v1'
        focused_modules = $focusedModules
        contract_manifest = 'tests/gates/v07_phase_b_contract_manifest.json'
        architecture_manifest = 'tests/gates/v07_phase_b_architecture_manifest.json'
        phase_a_gate = 'scripts/verify-v07-phase-a.ps1'
        fresh_replay_script = 'scripts/agent-kernel-replay-smoke.py'
        network_activity = $false
        provider_generation = $false
        phase_c_started = $phaseCStarted
    }
    Write-Output ('PHASE_B_MANIFEST=' + ($manifest | ConvertTo-Json -Compress))
    exit 0
}

$env:MACR_ROOT = $repoRoot
if (-not $env:MACR_STATE_ROOT) {
    $env:MACR_STATE_ROOT = 'D:\AI_RESIDENCE\AI_Runtime\macr-state'
}
$env:MACR_TEST_TMP = Join-Path $env:MACR_STATE_ROOT 'test-tmp'
$repoPythonPath = Join-Path $repoRoot 'src'
$env:PYTHONPATH = $repoPythonPath
$env:PYTHONDONTWRITEBYTECODE = '1'

$mutexName = 'Local\MACR_V07_PHASE_B_GATE'
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
        throw 'Timed out acquiring the MACR v0.7 Phase B verification mutex.'
    }

    $focusedOutput = @(python -m unittest @focusedModules -q 2>&1)
    $focusedExit = $LASTEXITCODE
    if ($focusedExit) {
        $focusedOutput
        exit $focusedExit
    }
    $focusedText = $focusedOutput -join "`n"
    $focusedMatch = [regex]::Matches($focusedText, 'Ran\s+(\d+)\s+tests') |
        Select-Object -Last 1
    if (-not $focusedMatch) {
        throw 'Could not parse the focused Phase B test count.'
    }
    $focusedCount = [int]$focusedMatch.Groups[1].Value

    python -m compileall -q (Join-Path $repoRoot 'src') (Join-Path $repoRoot 'tests')
    if ($LASTEXITCODE) { exit $LASTEXITCODE }

    $phaseAOutput = @(& (Join-Path $PSScriptRoot 'verify-v07-phase-a.ps1') 2>&1)
    $phaseAExit = $LASTEXITCODE
    if ($phaseAExit) {
        $phaseAOutput
        exit $phaseAExit
    }
    $phaseALine = $phaseAOutput |
        Where-Object { $_.ToString().StartsWith('PHASE_A_SUMMARY=') } |
        Select-Object -Last 1
    if (-not $phaseALine) {
        throw 'Phase A compatibility gate did not emit a summary.'
    }
    $phaseA = $phaseALine.ToString().Substring('PHASE_A_SUMMARY='.Length) |
        ConvertFrom-Json
    if ($phaseA.network_activity -ne $false -or
        $phaseA.provider_generation -ne $false -or
        $phaseA.phase_b_started -ne $true) {
        throw 'Phase A compatibility summary has invalid Phase B/offline flags.'
    }

    $testRoot = [System.IO.Path]::GetFullPath($env:MACR_TEST_TMP)
    if (-not $testRoot.StartsWith('D:\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Phase B test state must remain on D:.'
    }
    $subjectRoot = Join-Path $testRoot (
        'phase-b-gate-' + [guid]::NewGuid().ToString('N')
    )
    New-Item -ItemType Directory -Force -Path $subjectRoot | Out-Null
    try {
        $env:TEMP = Join-Path $subjectRoot 'temp'
        $env:TMP = $env:TEMP
        $env:PIP_CACHE_DIR = Join-Path $subjectRoot 'pip-cache'
        $wheelDir = Join-Path $subjectRoot 'wheel'
        $targetDir = Join-Path $subjectRoot 'installed'
        $runDir = Join-Path $subjectRoot 'run'
        New-Item -ItemType Directory -Force -Path (
            $env:TEMP,
            $env:PIP_CACHE_DIR,
            $wheelDir,
            $targetDir,
            $runDir
        ) | Out-Null

        $wheelOutput = @(python -m pip wheel $repoRoot --no-deps `
            --no-build-isolation --disable-pip-version-check `
            --wheel-dir $wheelDir 2>&1)
        if ($LASTEXITCODE) {
            $wheelOutput
            exit $LASTEXITCODE
        }
        $wheel = Get-ChildItem -LiteralPath $wheelDir -Filter '*.whl' |
            Select-Object -First 1
        if (-not $wheel) {
            throw 'Phase B wheel was not produced.'
        }
        $wheelSha256 = (Get-FileHash -LiteralPath $wheel.FullName `
            -Algorithm SHA256).Hash.ToLowerInvariant()

        $installOutput = @(python -m pip install --no-deps --no-index `
            --disable-pip-version-check --target $targetDir `
            $wheel.FullName 2>&1)
        if ($LASTEXITCODE) {
            $installOutput
            exit $LASTEXITCODE
        }

        $env:PYTHONPATH = $targetDir
        $smokeScript = Join-Path $PSScriptRoot 'agent-kernel-replay-smoke.py'
        $database = Join-Path $runDir 'agent.sqlite3'
        Push-Location $runDir
        try {
            $replayOutput = @(python -S $smokeScript --database $database 2>&1)
            $replayExit = $LASTEXITCODE
        }
        finally {
            Pop-Location
            $env:PYTHONPATH = $repoPythonPath
        }
        if ($replayExit) {
            $replayOutput
            exit $replayExit
        }
        $replay = ($replayOutput -join "`n") | ConvertFrom-Json
        if ($replay.reconstruction_equivalent -ne $true -or
            $replay.network_activity -ne $false -or
            $replay.provider_generation -ne $false) {
            throw 'Fresh Agent package replay did not establish offline equivalence.'
        }
    }
    finally {
        $env:PYTHONPATH = $repoPythonPath
        $resolvedSubject = [System.IO.Path]::GetFullPath($subjectRoot)
        $expectedPrefix = $testRoot.TrimEnd('\') + '\'
        if (-not $resolvedSubject.StartsWith(
            $expectedPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw 'Refusing to clean an unexpected Phase B test subject.'
        }
        if (Test-Path -LiteralPath $resolvedSubject) {
            Remove-Item -LiteralPath $resolvedSubject -Recurse -Force
        }
    }

    $doctorText = python -m macr_runtime doctor --config (
        Join-Path $repoRoot 'config\providers.json'
    )
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
        throw 'The Phase B verification subject must be a clean worktree.'
    }

    $contractManifest = Get-Content -LiteralPath (
        Join-Path $repoRoot 'tests\gates\v07_phase_b_contract_manifest.json'
    ) -Raw -Encoding UTF8 | ConvertFrom-Json

    $summary = [ordered]@{
        schema = 'macr-v07-phase-b-summary/v1'
        candidate_commit = (git -C $repoRoot rev-parse HEAD)
        candidate_tree = (git -C $repoRoot rev-parse 'HEAD^{tree}')
        agent_schema_version = [int]$replay.agent_schema_version
        focused_tests = $focusedCount
        required_test_ids = @($contractManifest.required).Count
        phase_a_focused_tests = [int]$phaseA.focused_tests
        inherited_tests = [int]$phaseA.inherited_tests
        bootstrap_processes = 32
        ownership_contenders = 8
        hard_exit_code = 73
        fresh_package_replay = $true
        final_state = $replay.final_state
        final_revision = [int]$replay.state_revision
        final_epoch = [int]$replay.epoch
        event_count = [int]$replay.event_count
        state_digest = $replay.state_digest
        replay_digest = $replay.replay_digest
        wheel_sha256 = $wheelSha256
        network_activity = $false
        provider_generation = $false
        git_clean = $true
        phase_c_started = $phaseCStarted
    }
    Write-Output ('PHASE_B_SUMMARY=' + (
        $summary | ConvertTo-Json -Compress -Depth 5
    ))
}
finally {
    if ($mutexAcquired) {
        $verificationMutex.ReleaseMutex()
    }
    $verificationMutex.Dispose()
}
exit 0
