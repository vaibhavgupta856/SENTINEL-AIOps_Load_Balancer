# Full Sentinel reset - stops native processes, clears stale registry, restarts Docker
# Usage: .\scripts\reset-cluster.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host ""
Write-Host "=== Sentinel cluster reset ===" -ForegroundColor Cyan
Write-Host ""

& (Join-Path $Root "scripts\stop-native.ps1")

Write-Host "Stopping Docker stack..." -ForegroundColor Yellow
docker compose down

$Registry = Join-Path $Root "orchestrator\node_registry.json"
if (Test-Path $Registry) {
    Remove-Item $Registry -Force
    Write-Host "Removed stale node_registry.json" -ForegroundColor DarkGray
}

Write-Host "Starting fresh Docker stack..." -ForegroundColor Yellow
docker compose up --build -d

Write-Host ""
Write-Host "Done. Wait ~30 seconds, then open http://localhost:5173" -ForegroundColor Green
Write-Host "If nodes were stuck, native URLs are cleared and workers re-registered." -ForegroundColor DarkGray
Write-Host ""
