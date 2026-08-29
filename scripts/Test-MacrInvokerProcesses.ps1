[CmdletBinding()]
param(
    [int]$ExpectedCount = -1
)

if ($PSBoundParameters.ContainsKey('ExpectedCount') -and $ExpectedCount -lt 0) {
    throw 'ExpectedCount must be non-negative.'
}

$predicate = '(?i)(?:invoke-glm\.ps1["'']?\s+-TaskPath(?:\s|[="'';]|$)|macr\.ps1["'']?\s+invoke\s+glm_flash_worker(?:\s|["'';]|$))'
$matchingPids = @(
    Get-CimInstance Win32_Process -ErrorAction Stop |
        Where-Object { $_.ProcessId -ne $PID } |
        Where-Object {
            $_.CommandLine -and $_.CommandLine -match $predicate
        } |
        ForEach-Object { [int]$_.ProcessId } |
        Sort-Object -Unique
)

$report = [ordered]@{
    predicate = $predicate
    census_pid = [int]$PID
    excluded_pid = [int]$PID
    matching_pids = @($matchingPids)
    count = [int]$matchingPids.Count
}

$report | ConvertTo-Json -Depth 4

if (
    $PSBoundParameters.ContainsKey('ExpectedCount') -and
    $matchingPids.Count -ne $ExpectedCount
) {
    exit 1
}

$global:LASTEXITCODE = 0
return
