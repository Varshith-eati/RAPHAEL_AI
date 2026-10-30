. (Join-Path $PSScriptRoot 'Runtime.ps1')
New-Item -ItemType Directory -Force -Path $appSettings.runtime | Out-Null
if ($appSettings.laptop_enabled -and -not (Test-Path -LiteralPath $appSettings.workspace)) {
    New-Item -ItemType Directory -Force -Path $appSettings.workspace | Out-Null
}
$running = $false
try {
    $status = Invoke-RestMethod -Uri "$appUrl/api/status" -TimeoutSec 2
    if ($status.app -ne $appSettings.app) { throw 'Another application is using the configured port.' }
    $running = $true
} catch {
    if ($_.Exception.Message -eq 'Another application is using the configured port.') { throw }
}
if (-not $running) {
    $arguments = @('-B', ('"' + $appEntry + '"'))
    Start-Process -FilePath $appPython -ArgumentList $arguments -WorkingDirectory $appDirectory -WindowStyle Hidden -RedirectStandardOutput (Join-Path $appSettings.runtime 'server.log') -RedirectStandardError (Join-Path $appSettings.runtime 'errors.log') | Out-Null
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Milliseconds 500
        try {
            $status = Invoke-RestMethod -Uri "$appUrl/api/status" -TimeoutSec 1
            if ($status.app -eq $appSettings.app) { $running = $true; break }
        } catch {}
    }
    if (-not $running) { throw 'Raphael did not start. Check runtime/errors.log.' }
}
Start-Process $appUrl
