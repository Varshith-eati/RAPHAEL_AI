. (Join-Path $PSScriptRoot 'Runtime.ps1')
Push-Location $appDirectory
try { & $appPython -B -m unittest discover -s tests -v; $testExit = $LASTEXITCODE }
finally { Pop-Location }
exit $testExit
