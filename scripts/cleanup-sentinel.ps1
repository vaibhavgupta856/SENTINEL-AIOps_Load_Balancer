# Stop ALL Sentinel processes (native + Docker) to prevent port conflicts.
# Usage: .\scripts\cleanup-sentinel.ps1

$ErrorActionPreference = "SilentlyContinue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "Cleaning up Sentinel (native + Docker)..." -ForegroundColor Yellow

$PidFile = Join-Path $Root "runtime\native\pids.txt"
if (Test-Path $PidFile) {
    Get-Content $PidFile | Where-Object { $_ -match '^\d+$' } | ForEach-Object {
        Stop-Process -Id ([int]$_) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $PidFile -Force
}

$ports = 8000, 5173, 8080, 8081, 8082, 8083, 8084, 8085, 8086, 8087
foreach ($port in $ports) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.OwningProcess -le 0) { return }
        $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
        if ($proc -and ($proc.ProcessName -like 'python*' -or $proc.ProcessName -eq 'node')) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            Write-Host "  Stopped $($proc.ProcessName) on port $port" -ForegroundColor DarkGray
        }
    }
}

if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker compose down 2>$null | Out-Null
}

Start-Sleep -Seconds 2
Write-Host "Cleanup done." -ForegroundColor Green
