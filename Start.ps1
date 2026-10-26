param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
$appData = Join-Path $appRoot 'data'
New-Item -ItemType Directory -Force -Path $appData | Out-Null
$venvPython = Join-Path $appRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPython) { $appPython = $venvPython }
else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw 'Install Python 3.11 or later, then run Start.cmd again. / 请安装 Python 3.11 或更新版本。' }
    $appPython = $pythonCommand.Source
}
$appURL = 'http://127.0.0.1:8765'
$running = $false
try {
    $health = Invoke-RestMethod -Uri "$appURL/api/health" -TimeoutSec 2
    if ($health.app -eq 'AcademicUpdater') { $running = $true }
} catch { }
if (-not $running) {
    $entry = Join-Path $appRoot 'run.py'
    $arguments = '"' + $entry + '" --port 8765'
    Start-Process -FilePath $appPython -ArgumentList $arguments -WorkingDirectory $appRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $appData 'server.log') -RedirectStandardError (Join-Path $appData 'server-error.log') | Out-Null
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 300
        try {
            $health = Invoke-RestMethod -Uri "$appURL/api/health" -TimeoutSec 1
            if ($health.app -eq 'AcademicUpdater') { $running = $true; break }
        } catch { }
    }
}
if (-not $running) { throw 'AcademicUpdater did not start. See data/server-error.log. / 启动失败，请检查 data/server-error.log。' }
if (-not $NoBrowser) { Start-Process $appURL }
Write-Output "AcademicUpdater is running at $appURL"
