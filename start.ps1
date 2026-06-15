# Sentinel AIOps — choose deployment mode
# Usage:
#   .\start.ps1 docker          # Docker dev (default)
#   .\start.ps1 docker -Prod    # Docker production
#   .\start.ps1 native          # No Docker — full demo locally
#   .\start.ps1 restart       # Full reset (fixes offline / duplicate starts)

param(
    [Parameter(Position = 0)]
    [ValidateSet("docker", "native", "stop", "restart")]
    [string]$Mode = "docker",

    [switch]$Prod
)

$ScriptDir = Join-Path $PSScriptRoot "scripts"

switch ($Mode) {
    "docker" {
        if ($Prod) {
            & (Join-Path $ScriptDir "start-docker.ps1") -Prod
        } else {
            & (Join-Path $ScriptDir "start-docker.ps1")
        }
    }
    "native" {
        & (Join-Path $ScriptDir "start-native.ps1")
    }
    "stop" {
        & (Join-Path $ScriptDir "stop-native.ps1")
    }
    "restart" {
        & (Join-Path $ScriptDir "reset-cluster.ps1")
    }
}
