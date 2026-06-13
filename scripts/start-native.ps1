# Sentinel AIOps — Native deployment mode (no Docker, full demo on one machine)
# Uses Python monitor_mock.py instead of C++ — works on Windows, Linux, macOS.
# Usage: .\scripts\start-native.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$RuntimeDir = Join-Path $Root "runtime\native"
$PidFile = Join-Path $RuntimeDir "pids.txt"

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Host "$Name is required but not found on PATH." -ForegroundColor Red
        exit 1
    }
}

function Start-BackgroundProcess($Label, $FilePath, $ArgumentList, $WorkingDirectory, $EnvVars) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = $ArgumentList
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    foreach ($key in $EnvVars.Keys) {
        if ($psi.EnvironmentVariables.ContainsKey($key)) {
            $psi.EnvironmentVariables[$key] = [string]$EnvVars[$key]
        } else {
            [void]$psi.EnvironmentVariables.Add($key, [string]$EnvVars[$key])
        }
    }
    $proc = [System.Diagnostics.Process]::Start($psi)
    Write-Host "  [$Label] PID $($proc.Id)" -ForegroundColor DarkGray
    return $proc.Id
}

Write-Host ""
Write-Host "=== Sentinel AIOps - Native mode (no Docker) ===" -ForegroundColor Cyan
Write-Host ""

Require-Command python

$npmCmdObj = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($npmCmdObj) {
    $npmCmd = $npmCmdObj.Source
} else {
    Require-Command npm
    $npmCmd = (Get-Command npm).Source
}

if (Test-Path $PidFile) {
    Write-Host "Native stack may already be running. Run .\scripts\stop-native.ps1 first." -ForegroundColor Yellow
    exit 1
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

Write-Host "Installing orchestrator dependencies..." -ForegroundColor Yellow
python -m pip install -q -r (Join-Path $Root "orchestrator\requirements.txt")

$DashboardNodeModules = Join-Path $Root "dashboard\node_modules"
if (-not (Test-Path $DashboardNodeModules)) {
    Write-Host "Installing dashboard dependencies..." -ForegroundColor Yellow
    Push-Location (Join-Path $Root "dashboard")
    npm install --silent
    Pop-Location
}

$pids = @()

Write-Host "Starting orchestrator on :8000..." -ForegroundColor Yellow
$pids += Start-BackgroundProcess "orchestrator" "python" "-m uvicorn master:app --host 0.0.0.0 --port 8000" `
    (Join-Path $Root "orchestrator") @{}

$nodes = @(
    @{ Id = "node1"; MonitorPort = 8080; ReceiverPort = 8081 },
    @{ Id = "node2"; MonitorPort = 8082; ReceiverPort = 8083 },
    @{ Id = "node3"; MonitorPort = 8084; ReceiverPort = 8085 },
    @{ Id = "node4"; MonitorPort = 8086; ReceiverPort = 8087 }
)

$ClusterDir = Join-Path $Root "cluster"
foreach ($node in $nodes) {
    $dataDir = Join-Path $RuntimeDir $node.Id
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

    $envBase = @{
        NODE_ID           = $node.Id
        NODE_HOST         = "127.0.0.1"
        NODE_PORT         = [string]$node.ReceiverPort
        MONITOR_PORT      = [string]$node.MonitorPort
        MONITOR_URL       = "http://127.0.0.1:$($node.MonitorPort)"
        WORKER_DATA_DIR   = $dataDir
        ORCHESTRATOR_URL  = "http://127.0.0.1:8000/api/nodes/register"
    }

    Write-Host "Starting $($node.Id) (monitor :$($node.MonitorPort), API :$($node.ReceiverPort))..." -ForegroundColor Yellow
    $pids += Start-BackgroundProcess "$($node.Id)-monitor" "python" "monitor_mock.py" $ClusterDir $envBase
    Start-Sleep -Milliseconds 300
    $pids += Start-BackgroundProcess "$($node.Id)-receiver" "python" "receiver.py" $ClusterDir $envBase
}

Write-Host "Starting dashboard on :5173..." -ForegroundColor Yellow
$pids += Start-BackgroundProcess "dashboard" $npmCmd "run dev -- --host 0.0.0.0" `
    (Join-Path $Root "dashboard") @{}

$pids | Out-File -FilePath $PidFile -Encoding utf8

Write-Host ""
Write-Host "Native stack is running." -ForegroundColor Green
Write-Host ""
Write-Host "  Dashboard : http://localhost:5173" -ForegroundColor Green
Write-Host "  API       : http://localhost:8000" -ForegroundColor Green
Write-Host "  Swagger   : http://localhost:8000/docs" -ForegroundColor Green
Write-Host ""
Write-Host "  4 worker nodes with thermal/latency/chaos/recovery - same features as Docker." -ForegroundColor DarkGray
Write-Host ""
Write-Host "Stop: .\scripts\stop-native.ps1" -ForegroundColor DarkGray
Write-Host ""
