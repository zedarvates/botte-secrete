# Read-only incident snapshot. Does not stop/restart processes or replay work.
[CmdletBinding()]
param([ValidateRange(5, 120)][int]$Minutes = 30)
$ErrorActionPreference = 'Stop'
$issues = [System.Collections.Generic.List[string]]::new()
$memory = $null
$commit = $null
try {
    $osInfo = Get-CimInstance Win32_OperatingSystem
    $memory = [ordered]@{
        totalPhysicalGiB = [math]::Round($osInfo.TotalVisibleMemorySize / 1MB, 2)
        availablePhysicalGiB = [math]::Round($osInfo.FreePhysicalMemory / 1MB, 2)
    }
} catch { $issues.Add('physical_memory_unavailable') }
try {
    $perfMemory = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
    $commit = [ordered]@{
        committedGiB = [math]::Round($perfMemory.CommittedBytes / 1GB, 2)
        limitGiB = [math]::Round($perfMemory.CommitLimit / 1GB, 2)
        availableGiB = [math]::Round(($perfMemory.CommitLimit - $perfMemory.CommittedBytes) / 1GB, 2)
    }
} catch { $issues.Add('commit_memory_unavailable') }
$codexProcesses = @(Get-Process | Where-Object { $_.ProcessName -match 'codex' } | ForEach-Object {
    [ordered]@{
        id = $_.Id
        name = $_.ProcessName
        hasWindow = ($_.MainWindowHandle -ne 0)
        windowResponding = $_.Responding
        workingSetGiB = [math]::Round($_.WorkingSet64 / 1GB, 3)
        privateGiB = [math]::Round($_.PrivateMemorySize64 / 1GB, 3)
        cpuSeconds = $_.CPU
    }
})
$since = (Get-Date).AddMinutes(-$Minutes)
$appEvents = @(Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=$since; Id=1000,1001,1002} -ErrorAction SilentlyContinue |
    Where-Object { $_.Message -match 'codex' } |
    Select-Object -First 10 | ForEach-Object {
        [ordered]@{ atUtc=$_.TimeCreated.ToUniversalTime().ToString('o'); id=$_.Id; provider=$_.ProviderName }
    })
$memoryEvents = @(Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Resource-Exhaustion-Detector'; Id=2004; StartTime=$since} -ErrorAction SilentlyContinue |
    Select-Object -First 10 | ForEach-Object {
        [ordered]@{ atUtc=$_.TimeCreated.ToUniversalTime().ToString('o'); id=$_.Id; provider=$_.ProviderName }
    })
[ordered]@{
    schema = 'botte.codex-windows-diagnostic/v1'
    measuredAtUtc = [datetime]::UtcNow.ToString('o')
    physicalMemory = $memory
    commitMemory = $commit
    codexProcesses = $codexProcesses
    applicationEvents = $appEvents
    resourceExhaustionEvents = $memoryEvents
    issues = @($issues.ToArray())
    limitations = @('Point-in-time snapshot, not a responsiveness test.',
                    'No event found does not prove absence of a crash.',
                    'WindowResponding applies only to visible Windows message loops.')
} | ConvertTo-Json -Depth 6
