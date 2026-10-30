$ErrorActionPreference = 'Stop'
$appDirectory = $PSScriptRoot
$appPython = Join-Path $appDirectory '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath (Join-Path $appDirectory 'engines\python\python.exe')) {
    $appPython = Join-Path $appDirectory 'engines\python\python.exe'
}
if (-not (Test-Path -LiteralPath $appPython)) {
    $appPython = Join-Path $appDirectory '..\raphael-chat\.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $appPython)) { throw 'Python runtime missing. See README.md for setup.' }
$appPython = (Resolve-Path -LiteralPath $appPython).Path
$appEntry = Join-Path $appDirectory 'server.py'
$appSettings = & $appPython -B $appEntry --describe | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $appSettings.url) { throw 'Invalid config.toml. Review the configuration error above.' }
$appUrl = $appSettings.url
$env:PYTHONDONTWRITEBYTECODE = '1'
