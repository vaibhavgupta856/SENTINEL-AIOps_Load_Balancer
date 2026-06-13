# Stop the native (non-Docker) Sentinel stack
# Usage: .\scripts\stop-native.ps1

$ErrorActionPreference = "SilentlyContinue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$PidFile = Join-Path $Root "runtime\native\pids.txt"

Write-Host ""
Write-Host "Stopping native Sentinel stack..." -ForegroundColor Yellow

if (-not (Test-Path $PidFile)) {
    Write-Host "No PID file found - nothing to stop." -ForegroundColor DarkGray
    exit 0
}

$pids = Get-Content $PidFile | Where-Object { $_ -match '^\d+$' }
foreach ($procId in $pids) {
    try {
        Stop-Process -Id ([int]$procId) -Force -ErrorAction Stop
        Write-Host "  Stopped PID $procId" -ForegroundColor DarkGray
    } catch {
        Write-Host "  PID $procId already exited" -ForegroundColor DarkGray
    }
}

Remove-Item $PidFile -Force
Write-Host "Done." -ForegroundColor Green
Write-Host ""
