# Stop the native (non-Docker) Sentinel stack
# Usage: .\scripts\stop-native.ps1

$ErrorActionPreference = "SilentlyContinue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$PidFile = Join-Path $Root "runtime\native\pids.txt"

Write-Host ""
Write-Host "Stopping native Sentinel stack..." -ForegroundColor Yellow

if (Test-Path $PidFile) {
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
}

foreach ($port in 8000,5173,8080,8081,8082,8083,8084,8085,8086,8087) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $conns) {
        if ($conn.OwningProcess -gt 0) {
            $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
            if ($proc -and ($proc.ProcessName -like 'python*' -or $proc.ProcessName -eq 'node')) {
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                Write-Host "  Stopped $($proc.ProcessName) on port $port (PID $($proc.Id))" -ForegroundColor DarkGray
            }
        }
    }
}

Write-Host "Done." -ForegroundColor Green
Write-Host ""
