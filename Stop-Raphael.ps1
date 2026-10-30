. (Join-Path $PSScriptRoot 'Runtime.ps1')
& $appPython -E -s -B (Join-Path $PSScriptRoot 'desktop.py') --exit
if ($LASTEXITCODE -eq 0) { Write-Host 'Raphael is stopping.'; return }
try {
    $status = Invoke-RestMethod -Uri "$appUrl/api/status" -TimeoutSec 3
    if ($status.app -ne $appSettings.app) { throw 'This port is used by another application.' }
    Invoke-RestMethod -Uri "$appUrl/api/shutdown" -Method Post -Headers @{ 'X-Raphael-Token' = $status.token } -ContentType 'application/json' -Body '{}' -TimeoutSec 5 | Out-Null
    Write-Host 'Raphael is stopping. Its local model service is closing.'
} catch { Write-Host ('Raphael could not be reached: ' + $_.Exception.Message) }
