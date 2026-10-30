# HOW TO SETUP — Raphael AI

This guide explains how to install, launch, configure, develop, test, and troubleshoot Raphael on Windows.

> **Recommended:** Use the complete portable package if you have it. A GitHub clone contains source code but excludes the large runtime and model assets.

## Contents

1. [Choose your setup method](#1-choose-your-setup-method)
2. [Method A — Complete portable package](#2-method-a--complete-portable-package-recommended)
3. [Method B — GitHub clone with bundled assets](#3-method-b--github-clone-with-bundled-assets)
4. [Method C — Manual Python environment](#4-method-c--manual-python-environment-advanced)
5. [Run in VS Code](#5-run-in-vs-code)
6. [Windows startup](#6-enable-or-disable-windows-startup)
7. [Voice and floating orb controls](#7-voice-and-floating-orb-controls)
8. [Run tests](#8-run-tests)
9. [Troubleshooting](#9-troubleshooting)
10. [Safe upgrades and privacy](#10-safe-upgrades-and-privacy)

## 1. Choose your setup method

| Method | Best for | Extra setup |
|---|---|---|
| Complete portable package | Most users; quickest setup | Extract ZIP and launch |
| GitHub clone + copied runtime assets | Developers who want Git-based updates | Copy `engines/` and `models/` from the full package |
| Manual Python environment | Advanced development | Install Python, dependencies, and model assets separately |

### Requirements

- Windows x64. The supplied build was validated on Windows 11. macOS, Linux, and native Windows ARM are not supported by this portable bundle.
- 16 GB RAM is a practical recommendation for local chat and speech together.
- Allow about 8.1 GB for the full ZIP and 9.7 GB after extraction. Around 25 GB free is recommended for setup, runtime data, and updates.
- Chrome or Edge for the web interface. Chrome is used by automated browser integration tests.
- Working Windows audio drivers, a microphone for voice input, and speakers or headphones for output. Typed chat does not require a microphone.
- Internet access for downloads and opening online websites. Local models do not require a cloud API key.
- VS Code is optional. Node.js/npm are only needed for optional browser tests.

The complete package includes Python 3.12.14 x64, Ollama, pinned dependencies, Llama 3.2, Qwen 3.5 4B, Whisper base, and Kokoro voice assets. If using this complete package, separate installations of Python, Ollama, Java, Node.js/npm, or an API subscription are not required just to run Raphael.

## 2. Method A — Complete portable package (recommended)

### Step 1 — Extract the ZIP

1. Obtain the **complete Raphael ZIP**.
2. Extract the entire ZIP to a normal local folder, for example `C:\\Raphael`.
3. Do not run Raphael from inside the ZIP viewer.
4. Avoid `C:\\Program Files`, where write permissions can be restrictive.
5. Open the extracted `Raphael-Realtime-Project` folder. It should contain `desktop.py`, `config.toml`, `engines`, `models`, and `web`.

If you only downloaded the source code from GitHub, use Method B or Method C instead. The source repository does not contain the multi-gigabyte model and runtime folders.

### Step 2 — Start Raphael

**To open the interface and start the desktop companion:**

Double-click `Open-Raphael.cmd`.

**To start silently in the background:**

Double-click `Launch-Desktop.cmd`. Look for the Raphael icon in the Windows notification area. If it is not visible, open the tray overflow.

The first model load may take longer than later replies. Start with a typed message before trying voice features.

### Step 3 — Stop Raphael

- Right-click the Raphael tray icon and choose **Exit Raphael**, or
- Run `Stop-Desktop.cmd`.

Closing the browser or VS Code does not necessarily stop the background companion.

### Step 4 — Browser-only mode (alternative)

Run `Launch-Raphael.cmd` to use the browser-only version. Stop it with `Stop-Raphael.cmd`.

**Do not run browser-only and desktop modes simultaneously**, because they use the same default ports.

## 3. Method B — GitHub clone with bundled assets

The repository is available at:
`https://github.com/Varshith-eati/RAPHAEL_AI`

A Git clone/source ZIP excludes the large `engines/`, `models/`, and personal runtime data. The easiest developer setup is to copy `engines/` and `models/` from your complete package into the root of the clone.

### Step 1 — Clone the repository

Open PowerShell or the VS Code terminal:

```powershell
git clone https://github.com/Varshith-eati/RAPHAEL_AI.git
cd RAPHAEL_AI
```

Git is only required for cloning and contributing. You can also download the source ZIP from GitHub.

### Step 2 — Copy the bundled folders

From the complete portable package, copy these folders into the root of the cloned repository:

- `engines/`
- `models/`

Keep the repository's `config.toml`; its bundled paths are intended to point to these folders. The large runtime/model folders are ignored by Git and should not be committed.

### Step 3 — Launch

```powershell
.\Open-Raphael.cmd
```

Or run in the background:

```powershell
.\Launch-Desktop.cmd
```

If you do not have the complete package to copy from, use the manual setup below and supply all required local models yourself.

## 4. Method C — Manual Python environment (advanced)

This route is intended for developers who do not want to use the bundled Python runtime. It requires more configuration and is not as turnkey as the complete package.

### Step 1 — Install prerequisites

Install:

- Python 3.12, 64-bit
- Ollama for Windows
- Git, if you are cloning the repository

Python versions other than 3.12 have not been validated for this pinned dependency set.

### Step 2 — Clone the project

```powershell
git clone https://github.com/Varshith-eati/RAPHAEL_AI.git
cd RAPHAEL_AI
```

### Step 3 — Create a virtual environment and install dependencies

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
```

### Step 4 — Supply the local model assets

Provide the required local assets. You can copy the `models/` folder from the complete package. Otherwise, configure the required assets yourself:

- Ollama chat models: `llama3.2:latest` and `qwen3.5:4b`
- Kokoro voice model: `kokoro-v1.0.onnx` and `voices-v1.0.bin`
- A faster-whisper-compatible Whisper base directory containing `model.bin`, `config.json`, `tokenizer.json`, and `vocabulary.txt`

Model and dependency availability, terms, and licensing are governed by their upstream projects. Consult `THIRD-PARTY.md`.

### Step 5 — Configure `config.toml`

Update the existing `[chat]`, `[voice]`, and `[transcription]` sections so paths match the assets you actually supplied. Relative paths resolve from `config.toml`.

For a separately installed Ollama, set the chat executable to an empty string (`chat.executable = ""`) and set `chat.models_dir` to the normal local Ollama model store (commonly `~/.ollama/models`). Confirm these values match your own installation before running.

Raphael does not automatically download missing models at runtime.

### Step 6 — Launch with the virtual environment

```powershell
.\.venv\Scripts\python.exe -B .\desktop.py --open
```

**Important:** The launch scripts prefer `engines\\python\\python.exe` if a bundled interpreter exists. If you choose `.venv`, either remove/rename the bundled interpreter only if you understand the implications, or invoke the virtual-environment Python directly as shown above. The included VS Code tasks are configured for the bundled interpreter by default.

## 5. Run in VS Code

1. Open VS Code.
2. Select **File → Open Folder**.
3. Choose the project folder containing `desktop.py`—not its parent folder or the ZIP file.
4. Select **Terminal → New Terminal** and use PowerShell.
5. Run one of these commands:

```powershell
.\Open-Raphael.cmd
```

```powershell
.\Launch-Desktop.cmd
```

To stop:

```powershell
.\Stop-Desktop.cmd
```

The included `.vscode/tasks.json` provides tasks for opening the interface, running in the background, stopping Raphael, and running backend tests. These tasks expect the bundled `engines/` folder. If you use `.venv`, update the task interpreter path to `${workspaceFolder}/.venv/Scripts/python.exe`.

For a focused editor walkthrough, see `RUN-IN-VS-CODE.md`.

### Where to edit

- Browser layout: `web/index.html`
- Browser styling: `web/styles.css`
- Browser behavior: `web/app.js`
- Native orb: `raphael/desktop/orb.py`
- Desktop conversation behavior: `raphael/desktop/controller.py`
- Model and engine paths: `config.toml`

Restart Raphael after Python/configuration changes. Reload the browser after web UI edits.

## 6. Enable or disable Windows startup

### Enable startup

1. Start Raphael from the folder where you intend to keep it.
2. Open the Raphael tray menu (check the tray overflow if the icon is hidden).
3. Turn on **Start with Windows**. The same setting is available in native Background & Real-Time Interaction → General settings.
4. By default, Raphael waits about 15 seconds after sign-in, then starts quietly and initializes local wake recognition.

Enabling startup also enables background operation and wake listening. You can disable wake listening separately afterward.

No administrator access, manual registry editing, or Task Scheduler configuration is required. Raphael creates a `Raphael Companion.lnk` shortcut in the current user's Startup folder. Open that folder using **Win + R**, then enter:

```text
shell:startup
```

### Disable startup

Turn off **Start with Windows** in Raphael's settings or tray menu. This removes the shortcut for that installation but does not stop the current session. Choose **Exit Raphael** to stop it now.

If you move or rename the project folder:

1. Disable startup in the old copy.
2. Exit Raphael.
3. Move or extract the new copy.
4. Launch Raphael from the new location.
5. Enable startup again.

Windows Task Manager can independently disable startup apps.

### Crash recovery

The companion can retry abnormal exits after 5, 15, and 45 seconds, then stop retrying after repeated failures. Ten stable minutes reset the retry budget. Recovery can be disabled in General settings. An intentional Exit remains stopped until you launch Raphael again or sign in next time.

Logs are written to `runtime/recovery.log` and `runtime/raphael.log` when runtime logging is enabled/available.

## 7. Voice and floating orb controls

| Control | Action |
|---|---|
| `Ctrl + Alt + R` | Activate the floating orb and begin a voice session |
| `Ctrl + Alt + Esc` | Stop the active session and dismiss the orb |
| `Ctrl + Alt + M` | Mute the microphone immediately |
| Tray → Enable Hey Raphael | Enable local wake-phrase monitoring |
| Tray → Pause/Resume listening | Pause or resume listening |
| Tray → Settings → Voice | Choose microphone, voice, volume, and timing |

The orb uses different animations for listening, thinking, and speaking. The tray icon indicates when capture is active. Follow-up listening lasts eight seconds by default.

To use wake listening, enable **Hey Raphael**, unmute the microphone, choose the correct input device, allow Windows desktop-app microphone access, and wait for recognition to become ready. Say “Hey Raphael” followed by your question, or pause after the wake phrase and then ask.

Wake detection uses local Whisper transcription of detected utterances. It is not a dedicated tiny always-on wake-word model and cannot wake a powered-off or sleeping computer. The application does not save raw microphone recordings.

For browser calls, allow microphone access for the local Raphael site as well as Windows desktop apps. Headphones are recommended to reduce echo.

## 8. Run tests

### Backend test suite

With the complete package:

```powershell
.\Run-Tests.cmd
```

Or run the backend tests directly:

```powershell
.\engines\python\python.exe -E -s -B -m unittest discover -s tests -p "test_*.py" -q
```

### Desktop recovery test

```powershell
.\engines\python\python.exe -E -s -B .\tests\desktop-recovery.py
```

### Desktop/orb smoke test

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\engines\python\python.exe -E -s -B .\tests\desktop-smoke.py
Remove-Item Env:\QT_QPA_PLATFORM
```

### Optional browser tests

Install Node.js and npm, and make sure Chrome is installed:

```powershell
npm install
npm test
npm run test:interface
```

For the microphone mode integration test:

```powershell
$env:RAPHAEL_PYTHON = (Resolve-Path .\engines\python\python.exe).Path
node .\tests\microphone-modes.cjs
```

Run integration suites one at a time because they share test ports and hotkeys. See `docs/testing-report.md` for further commands and test limitations. Test scripts using fake audio do not verify your physical microphone.

## 9. Troubleshooting

| Problem | What to check |
|---|---|
| `Launch-Desktop.cmd` appears to do nothing | It launches silently. Check the tray and tray overflow, press `Ctrl + Alt + R`, or run `Open-Raphael.cmd`. |
| No response / port already in use | Exit other Raphael instances. Default interface port is `8768`; local model port is `11436`. |
| Python/runtime missing | Extract the complete ZIP, or configure a working `.venv` for source-only setup. |
| Missing Python module | Install `requirements.lock.txt` into the same Python environment used to run Raphael. |
| Chat, voice, or transcription model missing | Check `config.toml` and the `models/` folder. Missing models are not automatically downloaded at runtime. |
| Wake phrase does not respond | Enable Hey Raphael, unmute, select the right microphone, grant Windows microphone permission, and wait for recognition readiness. Try the keyboard shortcut to isolate wake-detection problems. |
| Browser microphone denied | Allow microphone access for the local Raphael website and Windows desktop apps. |
| Speech echoes or interrupts itself | Use headphones. Native audio capture does not provide built-in acoustic echo cancellation. |
| No spoken reply | Enable spoken replies or start a call; check output volume, output device, and local voice-model paths. |
| First response is slow | Local models may load on first use. Try the smaller model and close other heavy applications. |
| Shortcut does not work | Another application may own it. Use the tray's Activate action or choose another shortcut in settings. |
| Raphael does not start at sign-in | Check Start with Windows, Task Manager startup-app settings, the `shell:startup` shortcut, and whether the folder was moved. Allow time for startup delay and model loading. |
| GitHub clone behaves differently from full ZIP | Git excludes the bundled runtime and models. Copy those folders from the full package or complete the manual setup. |
| Windows blocks a downloaded launcher | Prefer the supplied `.cmd` launchers. If you trust the package, inspect the ZIP's Properties and unblock that file if appropriate. Do not disable system-wide security settings. |

## 10. Safe upgrades and privacy

- Keep a backup of the previous ZIP or folder before upgrading.
- Stop Raphael before replacing source files or migrating runtime settings.
- Do not mix old and new Python library folders.
- Keep `THIRD-PARTY.md` and upstream license notices with redistributed dependencies and model files.
- Do not expose the browser-only localhost interface to a network.
- Raphael's laptop tools have explicit boundaries: writes and folder creation require a reviewed proposal and approval; reads outside the approved workspace require approval and remain read-only.
- Raphael does not read inboxes, operate accounts, execute arbitrary shell commands, delete files, or install software.

## Additional documentation

- `RUN-IN-VS-CODE.md` — VS Code workflow
- `docs/laptop-access.md` — laptop tool permissions and boundaries
- `docs/performance-report.md` — performance measurements and limitations
- `docs/windows-startup.md` — startup and recovery details
- `docs/feature-checklist.md` — implemented and partial features
- `docs/testing-report.md` — test commands and evidence
- `THIRD-PARTY.md` — dependency and model notices
