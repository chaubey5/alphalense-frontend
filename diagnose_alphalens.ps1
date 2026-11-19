[CmdletBinding()]
param(
    [switch]$SkipExternal
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"
$failureCount = 0

function Write-Check {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Detail
    )

    $status = if ($Passed) { "PASS" } else { "FAIL" }
    Write-Host ("{0}: {1} {2}" -f $Name, $status, $Detail)
    if (!$Passed) {
        $script:failureCount++
    }
}

function Get-ListeningPids {
    param([int]$Port)

    @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
}

$backendPids = @(Get-ListeningPids -Port 8001)
$frontendPids = @(Get-ListeningPids -Port 3000)
Write-Check -Name "Port 8001" -Passed ($backendPids.Count -gt 0) -Detail "backend listener present"
Write-Check -Name "Port 3000" -Passed ($frontendPids.Count -gt 0) -Detail "frontend listener present"
$legacyPids = @(Get-ListeningPids -Port 8000)
if ($legacyPids.Count -gt 0) {
    Write-Warning "Legacy port 8000 has listener PID(s) $($legacyPids -join ', '); this diagnostic will not stop them."
}

$backendBase = "http://127.0.0.1:8001"
try {
    $health = Invoke-RestMethod -Uri "$backendBase/api/health" -TimeoutSec 10
    Write-Check -Name "Backend health" -Passed ($health.status -eq "ok") -Detail "GET /api/health"
    Write-Check -Name "MongoDB ping" -Passed ([bool]$health.database.connected) -Detail "connected=$($health.database.connected)"
} catch {
    Write-Check -Name "Backend health" -Passed $false -Detail "GET /api/health failed ($($_.Exception.GetType().Name))"
}

try {
    $quote = Invoke-RestMethod -Uri "$backendBase/api/quote/AAPL" -TimeoutSec 30
    $quoteOk = $quote.ticker -eq "AAPL" -and [double]$quote.price -gt 0
    Write-Check -Name "AAPL quote" -Passed $quoteOk -Detail "source=$($quote.source)"
} catch {
    Write-Check -Name "AAPL quote" -Passed $false -Detail "GET /api/quote/AAPL failed ($($_.Exception.GetType().Name))"
}

$apiSource = Get-Content (Join-Path $frontendDir "src\lib\api.js") -Raw
$devUrlPinned = $apiSource -match 'const developmentUrl\s*=\s*"http://localhost:8001"'
Write-Check -Name "Frontend development API" -Passed $devUrlPinned -Detail "development target is localhost:8001"

foreach ($envName in @(".env", ".env.local", ".env.development", ".env.development.local", ".env.example")) {
    $envFile = Join-Path $frontendDir $envName
    if (!(Test-Path $envFile)) {
        continue
    }
    $urlLine = Get-Content $envFile | Where-Object { $_ -match '^\s*REACT_APP_BACKEND_URL\s*=' } | Select-Object -First 1
    if (!$urlLine) {
        continue
    }
    $configuredUrl = ($urlLine -split "=", 2)[1].Trim().Trim('"').Trim("'").TrimEnd("/")
    $urlOk = $configuredUrl -eq "http://localhost:8001"
    Write-Check -Name "frontend/$envName URL" -Passed $urlOk -Detail "expected localhost:8001"
}

$frontendEnv = Join-Path $frontendDir ".env"
$wdsLine = if (Test-Path $frontendEnv) {
    Get-Content $frontendEnv | Where-Object { $_ -match '^\s*WDS_SOCKET_PORT\s*=' } | Select-Object -First 1
}
$wdsPort = if ($wdsLine) { ($wdsLine -split "=", 2)[1].Trim().Trim('"').Trim("'") } else { "" }
$wdsOk = !$wdsPort -or $wdsPort -eq "3000"
Write-Check -Name "Frontend dev websocket" -Passed $wdsOk -Detail "no conflicting websocket port override"

$backendEnv = Join-Path $backendDir ".env"
$corsLine = if (Test-Path $backendEnv) {
    Get-Content $backendEnv | Where-Object { $_ -match '^\s*CORS_ORIGINS\s*=' } | Select-Object -First 1
}
$corsOrigins = @()
if ($corsLine) {
    $corsOrigins = (($corsLine -split "=", 2)[1].Trim().Trim('"').Trim("'")) -split ","
} else {
    $corsOrigins = @("http://localhost:3000", "http://127.0.0.1:3000")
}
$corsOk = @($corsOrigins | ForEach-Object { $_.Trim() }) -contains "http://localhost:3000"
Write-Check -Name "Frontend CORS origin" -Passed $corsOk -Detail "http://localhost:3000"

try {
    $frontendResponse = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 10
    Write-Check -Name "Frontend HTTP" -Passed ([int]$frontendResponse.StatusCode -eq 200) -Detail "GET http://localhost:3000"
} catch {
    Write-Check -Name "Frontend HTTP" -Passed $false -Detail "GET localhost:3000 failed ($($_.Exception.GetType().Name))"
}

if (!$SkipExternal) {
    $venvPython = Join-Path $backendDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $pythonExe = $venvPython
    } else {
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        $pythonExe = if ($pythonCommand) { $pythonCommand.Source } else { $null }
    }
    if (!$pythonExe) {
        Write-Check -Name "External provider/Mongo diagnostics" -Passed $false -Detail "Python was not found"
    } else {
        Push-Location $backendDir
        try {
            & $pythonExe ".\diagnose_integrations.py" --live --mongo
            Write-Check -Name "External provider/Mongo diagnostics" -Passed ($LASTEXITCODE -eq 0) -Detail "live provider, Groq, MongoDB, and memory probes"
        } finally {
            Pop-Location
        }
    }
} else {
    Write-Host "External provider and MongoDB probes skipped by request."
}

if ($failureCount -gt 0) {
    Write-Host "Diagnostics completed with $failureCount failure(s)."
    exit 1
}
Write-Host "All requested AlphaLens diagnostics passed."
