# Sentinel AIOps — Docker deployment mode (full cluster + dashboard)
# Usage: .\scripts\start-docker.ps1 [-Prod]

param(
    [switch]$Prod
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host ""
Write-Host "=== Sentinel AIOps - Docker mode ===" -ForegroundColor Cyan
Write-Host ""

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker is not installed or not on PATH." -ForegroundColor Red
    exit 1
}

& (Join-Path $Root "scripts\cleanup-sentinel.ps1")

if ($Prod) {
    Write-Host "Starting production stack (nginx :80)..." -ForegroundColor Yellow
    docker compose -f docker-compose.prod.yml up --build -d
    Write-Host ""
    Write-Host "Dashboard : http://localhost" -ForegroundColor Green
    Write-Host "API docs  : http://localhost/docs" -ForegroundColor Green
    Write-Host "Stop: docker compose -f docker-compose.prod.yml down" -ForegroundColor DarkGray
} else {
    Write-Host "Starting development stack (detached)..." -ForegroundColor Yellow
    docker compose up --build -d
    Write-Host ""
    Write-Host "Dashboard : http://localhost:5173" -ForegroundColor Green
    Write-Host "API       : http://localhost:8000" -ForegroundColor Green
    Write-Host "Swagger   : http://localhost:8000/docs" -ForegroundColor Green
    Write-Host ""
    Write-Host "Wait ~30s for all 4 nodes to register." -ForegroundColor DarkGray
    Write-Host "Stop: .\start.ps1 stop" -ForegroundColor DarkGray
}

Write-Host ""
