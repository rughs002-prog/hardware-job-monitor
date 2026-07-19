$ErrorActionPreference = "Stop"
$ProjectDirectory = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectDirectory
$env:PYTHONPATH = Join-Path $ProjectDirectory "src"

$LogDirectory = Join-Path $ProjectDirectory "logs"
New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
$LogFile = Join-Path $LogDirectory "monitor.log"

try {
    "[$(Get-Date -Format o)] Starting scan" | Add-Content -LiteralPath $LogFile
    python -m job_monitor.cli run 2>&1 | Out-File -LiteralPath $LogFile -Encoding utf8 -Append
    "[$(Get-Date -Format o)] Finished successfully" | Add-Content -LiteralPath $LogFile
}
catch {
    "[$(Get-Date -Format o)] Failed: $($_.Exception.Message)" | Add-Content -LiteralPath $LogFile
    throw
}
