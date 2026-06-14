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

& (Join-Path $Root "scripts\stop-native.ps1")

if ($Prod) {
    Write-Host "Starting production stack (nginx :80, 2 orchestrator workers)..." -ForegroundColor Yellow
    docker compose -f docker-compose.prod.yml up --build -d
    Write-Host ""
    Write-Host "Dashboard : http://localhost" -ForegroundColor Green
    Write-Host "API docs  : http://localhost/docs" -ForegroundColor Green
    Write-Host ""
    Write-Host "Stop: docker compose -f docker-compose.prod.yml down" -ForegroundColor DarkGray
} else {
    Write-Host "Starting development stack (Vite :5173, API :8000, 4 worker nodes)..." -ForegroundColor Yellow
    docker compose up --build
}
