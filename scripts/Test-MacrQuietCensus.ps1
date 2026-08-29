[CmdletBinding()]
param(
    [ValidateRange(1, 20)]
    [int]$ConsecutiveZeroSamples = 5,

    [ValidateRange(10, 5000)]
    [int]$IntervalMilliseconds = 250,

    [switch]$SkipMutex
)

$ErrorActionPreference = 'Stop'
$mutexName = 'Local\MACR_V06_QUIET_CENSUS'
$mutex = $null
$ownsMutex = $false
$failure = $null
$completedSamples = 0

try {
    if (-not $SkipMutex) {
        $mutex = [System.Threading.Mutex]::new($false, $mutexName)
        try {
            $ownsMutex = $mutex.WaitOne(30000)
        }
        catch [System.Threading.AbandonedMutexException] {
            $ownsMutex = $true
        }
        if (-not $ownsMutex) {
            throw 'Timed out acquiring the MACR quiet-census mutex.'
        }
    }

    $engine = (Get-Process -Id $PID -ErrorAction Stop).Path
    $censusPath = Join-Path $PSScriptRoot 'Test-MacrInvokerProcesses.ps1'
    for ($sample = 1; $sample -le $ConsecutiveZeroSamples; $sample++) {
        $censusText = & $engine `
            -NoProfile `
            -NonInteractive `
            -ExecutionPolicy Bypass `
            -File $censusPath `
            -ExpectedCount 0
        $censusExit = $LASTEXITCODE
        $report = $censusText | ConvertFrom-Json
        if ($censusExit -ne 0 -or [int]$report.count -ne 0) {
            $failure = [ordered]@{
                status = 'quiet_census_failed'
                sample = [int]$sample
                count = [int]$report.count
                matching_pids = @($report.matching_pids | ForEach-Object { [int]$_ })
            }
            break
        }
        $completedSamples = $sample
        if ($sample -lt $ConsecutiveZeroSamples) {
            Start-Sleep -Milliseconds $IntervalMilliseconds
        }
    }
}
finally {
    if ($ownsMutex -and $null -ne $mutex) {
        $mutex.ReleaseMutex()
    }
    if ($null -ne $mutex) {
        $mutex.Dispose()
    }
}

if ($null -ne $failure) {
    $failure | ConvertTo-Json -Depth 4
    exit 1
}

[ordered]@{
    status = 'quiet_census_passed'
    count = 0
    matching_pids = @()
    consecutive_zero_samples = [int]$completedSamples
    interval_milliseconds = [int]$IntervalMilliseconds
} | ConvertTo-Json -Depth 4
exit 0
