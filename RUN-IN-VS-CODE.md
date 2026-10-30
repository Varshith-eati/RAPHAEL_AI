# Run Raphael 0.6.2 in VS Code (Windows)

The **full project ZIP** includes Python, Ollama, speech libraries and the local models. You do not need to install Python packages or supply an API key for this package. Extract the entire ZIP before running it; allow about 10 GB for the extracted folder in addition to the ZIP.

1. Extract to a normal local folder, for example `C:\Raphael`.
2. In VS Code, use **File → Open Folder** and select the extracted `Raphael-Realtime-Project` folder that contains `desktop.py`, `config.toml`, `engines` and `models`.
3. Stop any older Raphael instance using its tray **Exit Raphael** command. Both copies use the same local ports by default.
4. Open **Terminal → New Terminal**. Select PowerShell and run one of the commands below from the project folder.

Open the full interface with the background companion:

```powershell
.\Open-Raphael.cmd
```

Start silently in the system tray:

```powershell
.\Launch-Desktop.cmd
```

Press **Ctrl+Alt+R** for the floating orb, **Ctrl+Alt+Esc** to dismiss it, and **Ctrl+Alt+M** to mute. Right-click Raphael's tray icon to enable **Hey Raphael**, choose your microphone, or open settings. The orb stays hidden until activation. Speech recognition and answers run locally; first use takes longer while models load.

Stop the companion and its local services:

```powershell
.\Stop-Desktop.cmd
```

The original browser-only interface is also available through `Launch-Raphael.cmd`. Stop the desktop companion first; do not run both versions on the same ports.

## Run Python directly

For a foreground development launch, use the bundled interpreter:

```powershell
.\engines\python\python.exe -E -s -B .\desktop.py --open
```

That terminal remains occupied while the supervisor is running. Use the tray **Exit Raphael** or `Stop-Desktop.cmd` in a second terminal to stop cleanly. Do not use the system Python by accident: it may not have Raphael's dependencies.

The included VS Code tasks provide **Raphael: Open interface**, **Raphael: Background**, **Raphael: Stop**, and **Raphael: Backend tests**. Use **Terminal → Run Task** to select one. These tasks do not require the Python extension.

If you want Python editor features, install Microsoft's Python extension, use **Python: Select Interpreter → Enter interpreter path**, and select `engines\python\python.exe` in this project. Running and editing are supported; a debugger configuration is not included.

## Edit and test

- Browser interface: `web/index.html`, `web/styles.css`, `web/app.js`.
- Floating orb: `raphael/desktop/orb.py`.
- Background conversation: `raphael/desktop/controller.py`.
- Windows integration and recovery: `raphael/desktop/windows.py`, `raphael/desktop/recovery.py`.
- Model paths and ports: `config.toml`.

Stop and restart Raphael after Python or configuration edits. Reload the browser after web-interface edits. Local memory and saved settings live in `runtime`; your dedicated files folder is `Documents\Raphael Workspace`.

Run the backend tests:

```powershell
.\engines\python\python.exe -E -s -B -m unittest discover -s tests -p "test_*.py" -q
```

Run the real Windows startup/recovery test without using your microphone:

```powershell
.\engines\python\python.exe -E -s -B .\tests\desktop-recovery.py
```

Run the Qt orb/conversation test with simulated audio:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\engines\python\python.exe -E -s -B .\tests\desktop-smoke.py
Remove-Item Env:\QT_QPA_PLATFORM
```

## Startup after moving or extracting the project

This download excludes personal settings, logs and startup registrations. New extractions start with startup and wake listening off. The already-configured copy on your laptop remains registered at its existing location.

To use the new extracted location at sign-in, disable **Start with Windows** in the old copy, exit it, open the new copy, then enable **Start with Windows** there. This also enables local wake listening. Keep the project at that location. You can disable startup again from its tray or settings.

If launch fails, check `runtime\raphael.log` and `runtime\recovery.log`. A port conflict usually means another Raphael copy is still running. For a microphone problem, check the selected device, Windows desktop-app microphone permission, and the tray mute state.

The small **source-only ZIP** does not include `engines` or `models`. Use the full ZIP for the commands above. Source-only setup requires a compatible Python environment, `requirements.lock.txt`, and your own local model paths; see `README.md`.
