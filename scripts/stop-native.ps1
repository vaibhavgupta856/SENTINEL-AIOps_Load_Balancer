# Stop the native (non-Docker) Sentinel stack AND Docker stack
# Usage: .\scripts\stop-native.ps1  OR  .\start.ps1 stop

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
& (Join-Path $Root "scripts\cleanup-sentinel.ps1")
