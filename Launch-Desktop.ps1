param([switch]$Open)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Runtime.ps1')
$desktopEntry = Join-Path $PSScriptRoot 'desktop.py'
$desktopPython = Join-Path (Split-Path -Parent $appPython) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $desktopPython)) { $desktopPython = $appPython }
$desktopArguments = @('-E', '-s', '-B', ('"' + $desktopEntry + '"'))
if ($Open) { $desktopArguments += '--open' } else { $desktopArguments += '--background' }
Start-Process -FilePath $desktopPython -ArgumentList $desktopArguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden | Out-Null
