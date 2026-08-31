[CmdletBinding()]
param(
    [switch]$ManifestOnly
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$focusedModules = @(
    'tests.test_semantic_contracts',
    'tests.test_agent_contract_boundaries',
    'tests.test_semantic_registry',
    'tests.test_semantic_graph',
    'tests.test_semantic_database',
    'tests.test_semantic_store',
    'tests.test_semantic_patch_validation',
    'tests.test_semantic_patch_compiler',
    'tests.test_semantic_proposals',
    'tests.test_semantic_commit',
    'tests.test_semantic_atomicity',
    'tests.test_semantic_shared_graph',
    'tests.test_semantic_multiprocess',
    'tests.test_semantic_rebuild',
    'tests.test_semantic_projection',
    'tests.integration.test_semantic_goal_to_plan',
    'tests.test_v07_phase_c_manifest'
)

if ($ManifestOnly) {
    $manifest = [ordered]@{
        schema = 'macr-v07-phase-c-wrapper-manifest/v1'
        focused_modules = $focusedModules
        contract_manifest = 'tests/gates/v07_phase_c_contract_manifest.json'
        architecture_manifest = 'tests/gates/v07_phase_c_architecture_manifest.json'
        phase_b_gate = 'scripts/verify-v07-phase-b.ps1'
        fresh_replay_script = 'scripts/semantic-working-state-replay-smoke.py'
        network_activity = $false
        provider_generation = $false
        phase_d_started = $false
    }
    Write-Output ('PHASE_C_MANIFEST=' + ($manifest | ConvertTo-Json -Compress))
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

$architectureManifestPath = Join-Path $repoRoot (
    'tests\gates\v07_phase_c_architecture_manifest.json'
)
$architectureManifest = Get-Content -LiteralPath $architectureManifestPath `
    -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($relative in @($architectureManifest.phase_d_forbidden_paths)) {
    if (Test-Path -LiteralPath (Join-Path $repoRoot $relative)) {
        throw "Phase D source is present: $relative"
    }
}

$mutexName = 'Local\MACR_V07_PHASE_C_GATE'
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
        throw 'Timed out acquiring the MACR v0.7 Phase C verification mutex.'
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
        throw 'Could not parse the focused Phase C test count.'
    }
    $focusedCount = [int]$focusedMatch.Groups[1].Value

    python -m compileall -q (Join-Path $repoRoot 'src') (Join-Path $repoRoot 'tests')
    if ($LASTEXITCODE) { exit $LASTEXITCODE }

    $phaseBOutput = @(& (Join-Path $PSScriptRoot 'verify-v07-phase-b.ps1') 2>&1)
    $phaseBExit = $LASTEXITCODE
    if ($phaseBExit) {
        $phaseBOutput
        exit $phaseBExit
    }
    $phaseBLine = $phaseBOutput |
        Where-Object { $_.ToString().StartsWith('PHASE_B_SUMMARY=') } |
        Select-Object -Last 1
    if (-not $phaseBLine) {
        throw 'Phase B compatibility gate did not emit a summary.'
    }
    $phaseB = $phaseBLine.ToString().Substring('PHASE_B_SUMMARY='.Length) |
        ConvertFrom-Json
    if ($phaseB.network_activity -ne $false -or
        $phaseB.provider_generation -ne $false -or
        $phaseB.phase_c_started -ne $true) {
        throw 'Phase B compatibility summary has invalid Phase C/offline flags.'
    }

    $testRoot = [System.IO.Path]::GetFullPath($env:MACR_TEST_TMP)
    if (-not $testRoot.StartsWith(
        'D:\', [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw 'Phase C test state must remain on D:.'
    }
    $subjectRoot = Join-Path $testRoot (
        'phase-c-gate-' + [guid]::NewGuid().ToString('N')
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
            throw 'Phase C wheel was not produced.'
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
        $env:MACR_INSTALL_TARGET = $targetDir
        $importProbeCode = @'
import os, pathlib, macr_runtime, macr_runtime.semantic as semantic_package
root = pathlib.Path(os.environ["MACR_INSTALL_TARGET"]).resolve()
paths = [pathlib.Path(macr_runtime.__file__).resolve(), pathlib.Path(semantic_package.__file__).resolve()]
assert all(path == root or root in path.parents for path in paths)
print("installed-import-isolated")
'@
        Push-Location $runDir
        try {
            $importProbeOutput = @($importProbeCode | python -S - 2>&1)
            $importProbeExit = $LASTEXITCODE
            if ($importProbeExit) {
                $importProbeOutput
                exit $importProbeExit
            }
            if (($importProbeOutput -join "`n").Trim() -ne 'installed-import-isolated') {
                throw 'Installed import isolation probe returned an unexpected result.'
            }

            $smokeScript = Join-Path $PSScriptRoot (
                'semantic-working-state-replay-smoke.py'
            )
            $firstOutput = @(python -S $smokeScript --database (
                Join-Path $runDir 'agent-first.sqlite3'
            ) 2>&1)
            $firstExit = $LASTEXITCODE
            if ($firstExit) {
                $firstOutput
                exit $firstExit
            }
            $secondOutput = @(python -S $smokeScript --database (
                Join-Path $runDir 'agent-second.sqlite3'
            ) 2>&1)
            $secondExit = $LASTEXITCODE
            if ($secondExit) {
                $secondOutput
                exit $secondExit
            }
        }
        finally {
            Pop-Location
            $env:PYTHONPATH = $repoPythonPath
            Remove-Item Env:MACR_INSTALL_TARGET -ErrorAction SilentlyContinue
        }
        $firstReplayText = ($firstOutput -join "`n").Trim()
        $secondReplayText = ($secondOutput -join "`n").Trim()
        if ($firstReplayText -cne $secondReplayText) {
            throw 'Fresh installed Phase C replays were not byte-identical.'
        }
        $replay = $firstReplayText | ConvertFrom-Json
        if ($replay.reconstruction_equivalent -ne $true -or
            $replay.network_activity -ne $false -or
            $replay.provider_generation -ne $false -or
            $replay.graph_revision -ne 2 -or
            $replay.semantic_binding_event_count -ne 2) {
            throw 'Fresh installed Phase C replay did not establish equivalence.'
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
            throw 'Refusing to clean an unexpected Phase C test subject.'
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
        throw 'The Phase C verification subject must be a clean worktree.'
    }

    $contractManifest = Get-Content -LiteralPath (
        Join-Path $repoRoot 'tests\gates\v07_phase_c_contract_manifest.json'
    ) -Raw -Encoding UTF8 | ConvertFrom-Json
    $summary = [ordered]@{
        schema = 'macr-v07-phase-c-summary/v1'
        candidate_commit = (git -C $repoRoot rev-parse HEAD)
        candidate_tree = (git -C $repoRoot rev-parse 'HEAD^{tree}')
        agent_schema_version = [int]$replay.agent_schema_version
        semantic_schema_version = [int]$replay.semantic_schema_version
        focused_tests = $focusedCount
        required_test_ids = @($contractManifest.required).Count
        phase_b_focused_tests = [int]$phaseB.focused_tests
        phase_a_focused_tests = [int]$phaseB.phase_a_focused_tests
        inherited_tests = [int]$phaseB.inherited_tests
        bootstrap_processes = 32
        semantic_commit_contenders = 8
        attach_fault_points = 2
        commit_fault_points = 6
        fresh_package_replay = $true
        installed_import_isolated = $true
        agent_state_revision = [int]$replay.agent_state_revision
        agent_epoch = [int]$replay.agent_epoch
        agent_event_count = [int]$replay.agent_event_count
        semantic_binding_event_count = [int]$replay.semantic_binding_event_count
        graph_revision = [int]$replay.graph_revision
        graph_revision_count = [int]$replay.graph_revision_count
        semantic_event_count = [int]$replay.semantic_event_count
        agent_state_digest = $replay.agent_state_digest
        semantic_binding_digest = $replay.semantic_binding_digest
        graph_digest = $replay.graph_digest
        projection_digest = $replay.projection_digest
        attach_receipt_digest = $replay.attach_receipt_digest
        commit_receipt_digest = $replay.commit_receipt_digest
        replay_digest = $replay.replay_digest
        wheel_sha256 = $wheelSha256
        network_activity = $false
        provider_generation = $false
        phase_d_started = $false
        git_clean = $true
    }
    Write-Output ('PHASE_C_SUMMARY=' + (
        $summary | ConvertTo-Json -Compress -Depth 6
    ))
}
finally {
    if ($mutexAcquired) {
        $verificationMutex.ReleaseMutex()
    }
    $verificationMutex.Dispose()
}
exit 0
