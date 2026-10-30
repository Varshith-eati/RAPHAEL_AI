@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-Desktop.ps1" -Open
if errorlevel 1 pause
