[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$stateFile = Join-Path $projectRoot ".alphalens\processes.json"

if (!(Test-Path $stateFile)) {
    Write-Host "No AlphaLens startup process state was found. Manually started or unrelated services were left untouched."
    exit 0
}

$state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
if ($state.projectRoot -ne $projectRoot) {
    throw "Refusing to use a process state file from another project path."
}

$processSnapshot = @(Get-CimInstance Win32_Process)
$script:stopOrder = New-Object 'System.Collections.Generic.List[int]'
$script:visitedProcessIds = @{}

function Add-DescendantsFirst {
    param([int]$ParentId)

    foreach ($child in @($script:processSnapshot | Where-Object {
        [int]$_.ParentProcessId -eq $ParentId
    })) {
        $childId = [int]$child.ProcessId
        if ($script:visitedProcessIds.ContainsKey($childId)) {
            continue
        }
        $script:visitedProcessIds[$childId] = $true
        Add-DescendantsFirst -ParentId $childId
        $script:stopOrder.Add($childId)
    }
}

function Test-ExpectedProcess {
    param(
        [string]$Role,
        $ProcessInfo
    )

    if (!$ProcessInfo -or !$ProcessInfo.CommandLine) {
        return $false
    }
    if ($Role -eq "backend") {
        $backendDir = Join-Path $projectRoot "backend"
        return (
            $ProcessInfo.Name -ieq "python.exe" -and
            $ProcessInfo.CommandLine.IndexOf($backendDir, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
            $ProcessInfo.CommandLine -match "uvicorn\s+server:app"
        )
    }
    $frontendDir = Join-Path $projectRoot "frontend"
    return (
        $ProcessInfo.Name -ieq "node.exe" -and
        $ProcessInfo.CommandLine.IndexOf($frontendDir, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $ProcessInfo.CommandLine -match "@craco[\\/]craco[\\/]dist[\\/]scripts[\\/]start\.js"
    )
}

$validRoots = 0
foreach ($entry in @($state.processes)) {
    $processId = [int]$entry.processId
    $rootProcess = $processSnapshot | Where-Object { [int]$_.ProcessId -eq $processId } | Select-Object -First 1
    if (!(Test-ExpectedProcess -Role $entry.role -ProcessInfo $rootProcess)) {
        Write-Warning "Skipping PID $processId because it is no longer the recorded AlphaLens $($entry.role) process."
        continue
    }
    $validRoots++
    $script:visitedProcessIds[$processId] = $true
    Add-DescendantsFirst -ParentId $processId
    $script:stopOrder.Add($processId)
}

foreach ($processId in $script:stopOrder) {
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped AlphaLens-owned PID $processId."
}

if ($validRoots -gt 0) {
    Start-Sleep -Milliseconds 500
}
Remove-Item -LiteralPath $stateFile -Force
Write-Host "Stopped only processes launched by start_alphalens.ps1. Other listeners were not touched."
