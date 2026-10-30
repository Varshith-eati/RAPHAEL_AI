@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0Runtime.ps1'; & $appPython -E -s -B (Join-Path '%~dp0' 'desktop.py') --exit"
