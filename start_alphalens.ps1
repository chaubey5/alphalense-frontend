[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"
$stateDir = Join-Path $projectRoot ".alphalens"
$stateFile = Join-Path $stateDir "processes.json"
$logDir = Join-Path $stateDir "logs"

function Get-ProjectProcessInfo {
    param([int]$ProcessId)

    Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
}

function Test-ManagedProcess {
    param(
        [string]$Role,
        $ProcessInfo
    )

    if (!$ProcessInfo -or !$ProcessInfo.CommandLine) {
        return $false
    }

    if ($Role -eq "backend") {
        return (
            $ProcessInfo.Name -ieq "python.exe" -and
            $ProcessInfo.CommandLine.IndexOf($backendDir, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
            $ProcessInfo.CommandLine -match "uvicorn\s+server:app"
        )
    }

    return (
        $ProcessInfo.Name -ieq "node.exe" -and
        $ProcessInfo.CommandLine.IndexOf($frontendDir, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $ProcessInfo.CommandLine -match "@craco[\\/]craco[\\/]dist[\\/]scripts[\\/]start\.js"
    )
}

function Get-PortListeners {
    param([int]$Port)

    $connections = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    foreach ($connection in $connections) {
        $processInfo = Get-ProjectProcessInfo -ProcessId $connection.OwningProcess
        [pscustomobject]@{
            Port = $Port
            ProcessId = [int]$connection.OwningProcess
            ProcessInfo = $processInfo
        }
    }
}

function Assert-PortAvailableOrProjectOwned {
    param(
        [int]$Port,
        [string]$Role
    )

    $listeners = @(Get-PortListeners -Port $Port)
    foreach ($listener in $listeners) {
        if (!(Test-ManagedProcess -Role $Role -ProcessInfo $listener.ProcessInfo)) {
            $name = if ($listener.ProcessInfo) { $listener.ProcessInfo.Name } else { "unknown process" }
            throw "Port $Port is occupied by PID $($listener.ProcessId) ($name), not a verified AlphaLens $Role process. Nothing was stopped."
        }
    }
    return ($listeners.Count -gt 0)
}

function Save-ManagedProcesses {
    param([object[]]$Processes)

    $state = [pscustomobject]@{
        projectRoot = $projectRoot
        processes = @($Processes)
    }
    $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $stateFile -Encoding UTF8
}

if (!(Test-Path $backendDir)) {
    throw "Backend directory was not found: $backendDir"
}
if (!(Test-Path $frontendDir)) {
    throw "Frontend directory was not found: $frontendDir"
}

$venvPython = Join-Path $backendDir ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $pythonExe = $venvPython
} else {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if (!$pythonCommand) {
        throw "Python was not found. Create backend\.venv or install Python 3.11+ and add it to PATH."
    }
    $pythonExe = $pythonCommand.Source
    Write-Warning "backend\.venv was not found; using Python from PATH."
}

$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (!$nodeCommand -or !$npmCommand) {
    throw "Node.js and npm are required and must be available on PATH."
}
Write-Host "Python: $(& $pythonExe --version 2>&1)"
Write-Host "Node.js: $(& $nodeCommand.Source --version)"
Write-Host "npm: $(& $npmCommand.Source --version)"

& $pythonExe -c "import fastapi, uvicorn, httpx, openai, pymongo, dotenv"
if ($LASTEXITCODE -ne 0) {
    throw "Backend dependencies are missing from the selected Python environment. Install backend\requirements.txt first."
}
$reactStart = Join-Path $frontendDir "node_modules\@craco\craco\dist\scripts\start.js"
if (!(Test-Path $reactStart)) {
    throw "Frontend dependencies are missing. Run npm ci in the frontend directory first."
}

$backendAlreadyRunning = Assert-PortAvailableOrProjectOwned -Port 8001 -Role "backend"
$frontendAlreadyRunning = Assert-PortAvailableOrProjectOwned -Port 3000 -Role "frontend"

if (!(Test-Path $stateDir)) {
    New-Item -ItemType Directory -Path $stateDir | Out-Null
}
if (!(Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

$managed = @()
if (Test-Path $stateFile) {
    $previous = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    if ($previous.projectRoot -ne $projectRoot) {
        throw "The process state file belongs to a different project path: $stateFile"
    }
    foreach ($entry in @($previous.processes)) {
        $processInfo = Get-ProjectProcessInfo -ProcessId ([int]$entry.processId)
        if (Test-ManagedProcess -Role $entry.role -ProcessInfo $processInfo) {
            $managed += $entry
        }
    }
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
if (!$backendAlreadyRunning) {
    $backendProcess = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @("-m", "uvicorn", "server:app", "--reload", "--host", "127.0.0.1", "--port", "8001") `
        -WorkingDirectory $backendDir `
        -RedirectStandardOutput (Join-Path $logDir "backend-$stamp.out.log") `
        -RedirectStandardError (Join-Path $logDir "backend-$stamp.err.log") `
        -WindowStyle Hidden `
        -PassThru
    $managed += [pscustomobject]@{ role = "backend"; processId = $backendProcess.Id }
    Save-ManagedProcesses -Processes $managed
    Write-Host "Started backend (PID $($backendProcess.Id))."
} else {
    Write-Host "Backend already running on port 8001; no duplicate was started."
}

if (!$frontendAlreadyRunning) {
    $oldPort = $env:PORT
    $oldHost = $env:HOST
    $oldBrowser = $env:BROWSER
    $oldWdsSocketPort = $env:WDS_SOCKET_PORT
    try {
        $env:PORT = "3000"
        $env:HOST = "127.0.0.1"
        $env:BROWSER = "none"
        $env:WDS_SOCKET_PORT = "3000"
        $frontendProcess = Start-Process `
            -FilePath $nodeCommand.Source `
            -ArgumentList @($reactStart) `
            -WorkingDirectory $frontendDir `
            -RedirectStandardOutput (Join-Path $logDir "frontend-$stamp.out.log") `
            -RedirectStandardError (Join-Path $logDir "frontend-$stamp.err.log") `
            -WindowStyle Hidden `
            -PassThru
    } finally {
        $env:PORT = $oldPort
        $env:HOST = $oldHost
        $env:BROWSER = $oldBrowser
        $env:WDS_SOCKET_PORT = $oldWdsSocketPort
    }
    $managed += [pscustomobject]@{ role = "frontend"; processId = $frontendProcess.Id }
    Save-ManagedProcesses -Processes $managed
    Write-Host "Started frontend (PID $($frontendProcess.Id))."
} else {
    Write-Host "Frontend already running on port 3000; no duplicate was started."
}

$backendReady = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/health" -TimeoutSec 3
        if ($health.status -eq "ok") {
            $backendReady = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (!$backendReady) {
    throw "Backend did not become healthy. See logs under .alphalens\logs. Stop script: .\stop_alphalens.ps1"
}

$frontendReady = $false
for ($attempt = 0; $attempt -lt 45; $attempt++) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 3
        if ([int]$response.StatusCode -eq 200) {
            $frontendReady = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (!$frontendReady) {
    throw "Frontend did not become ready. See logs under .alphalens\logs. Stop script: .\stop_alphalens.ps1"
}

Write-Host ""
Write-Host "AlphaLens is ready:"
Write-Host "  Frontend:  http://localhost:3000"
Write-Host "  Backend:   http://127.0.0.1:8001"
Write-Host "  API docs:  http://127.0.0.1:8001/docs"
Write-Host "  Stop:      .\stop_alphalens.ps1"
Write-Host "Logs: $logDir"
