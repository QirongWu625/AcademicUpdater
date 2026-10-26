$ErrorActionPreference = 'Stop'
$statePath = Join-Path $PSScriptRoot 'data\server.json'
if (-not (Test-Path -LiteralPath $statePath)) { Write-Output 'AcademicUpdater is not running.'; exit }
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$appProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$state.pid)" -ErrorAction SilentlyContinue
$entry = Join-Path $PSScriptRoot 'run.py'
if ($appProcess -and $appProcess.CommandLine.Contains($entry)) {
    Stop-Process -Id ([int]$state.pid)
    Write-Output 'AcademicUpdater stopped. Your database is preserved. / 应用已停止，数据已保留。'
} else { Write-Output 'No matching AcademicUpdater process is running.' }
