# Raphael 0.6.2 — local conversation and Windows startup companion

This upgrade preserves the existing sage interface, saved preferences, local models, laptop tools and human approvals. It adds streamed text, phrase-based speech, configurable interruption, timing diagnostics and an optional native Windows companion. Chat, recognition and voice stay on your computer.

**Start here:** [Requirements](#requirements) · [First run](#first-run-with-the-complete-package) · [VS Code](#run-and-edit-in-vs-code) · [GitHub/source setup](#run-a-github-clone-or-source-only-download) · [Windows startup](#enable-or-disable-windows-startup) · [Troubleshooting](#troubleshooting)

## Requirements

| Item | What you need |
| --- | --- |
| Operating system | Windows x64. The supplied build and startup integration were tested on Windows 11. Other Windows versions have not been validated; macOS/Linux and native Windows ARM are not supported by this portable bundle. |
| Processor | A modern x64 multicore CPU. A dedicated GPU is not required for the configured local speech pipeline; Ollama may use supported hardware automatically. |
| Memory | 16 GB RAM is a practical recommendation for local chat plus speech. This is not a formally tested minimum. Smaller-memory machines may need the smaller chat model and fewer running applications. |
| Disk space | Approximately 8.1 GB for the full ZIP and 9.7 GB extracted. Allow about 25 GB free for download, extraction, runtime data and updates. |
| Browser | Chrome or Edge for the main web interface. Automated browser integration tests specifically use installed Chrome. |
| Audio | Working Windows audio drivers, microphone permission for desktop apps, a microphone for voice input, and headphones/speakers for spoken output. Headphones help avoid echo. Text chat does not need a microphone. |
| VS Code | Optional for editing; not required to run Raphael. The Microsoft Python extension is optional for editor features. |
| Internet | Needed to obtain software/models if using a source-only setup, or to open online websites. The included chat, transcription and voice models run locally without a cloud API key. |

The **complete ZIP already includes** Python 3.12.14 x64, Ollama, the pinned Python libraries in `requirements.lock.txt`, Llama 3.2, Qwen 3.5 4B, Whisper base and Kokoro voice assets. You do **not** need a separate Python installation, a separate Ollama installation, Java, Node.js, npm or an API subscription for the complete package.

Node.js and Playwright are optional development tools used only for JavaScript/browser tests. Git is optional unless you want to clone or contribute to the GitHub repository. The package is portable; it is not a signed Windows installer and does not require installing a Windows service.

## First run with the complete package

1. Extract the **entire ZIP** to a normal local folder, for example `C:\Raphael`. Do not run it inside the ZIP viewer, and do not extract it into `Program Files`, where normal writes may be restricted.
2. Open the extracted `Raphael-Realtime-Project` folder. It must contain `desktop.py`, `config.toml`, `engines`, `models` and `web`.
3. If another Raphael copy is running, choose **Exit Raphael** from its tray menu first. The default interface port is **8768** and the local model port is **11436**.
4. Double-click **Open-Raphael.cmd** to open the main interface and start the background companion.
5. For a silent launch instead, double-click **Launch-Desktop.cmd**. Find its icon in the Windows notification area, including the tray overflow if necessary.
6. Start with a typed question. The first model load can take longer than later replies. Enable wake listening only when you want microphone monitoring.

Use the launcher or **Open Raphael** in the tray to open the interface. Desktop mode uses a private session link; typing only `http://127.0.0.1:8768/` into a fresh browser session may not connect with authorization.

To stop: choose **Exit Raphael** or run **Stop-Desktop.cmd**. Closing the browser or VS Code does not stop the default background companion. The browser-only alternative uses **Launch-Raphael.cmd** and **Stop-Raphael.cmd**; do not run it alongside the desktop companion on the same ports.

## Run and edit in VS Code

1. Open VS Code and choose **File → Open Folder**.
2. Select the project folder containing `desktop.py`, not the parent folder or the ZIP.
3. Choose **Terminal → New Terminal** and use PowerShell.
4. Open Raphael with:

```powershell
.\Open-Raphael.cmd
```

Or start silently:

```powershell
.\Launch-Desktop.cmd
```

Stop it cleanly with:

```powershell
.\Stop-Desktop.cmd
```

To run Python directly, using the bundled interpreter:

```powershell
.\engines\python\python.exe -E -s -B .\desktop.py --open
```

That terminal stays occupied while the supervisor runs. Stop from the tray or a second terminal. For editor features, install the Microsoft Python extension, run **Python: Select Interpreter → Enter interpreter path**, and select this project's `engines\python\python.exe`.

The included `.vscode/tasks.json` adds **Raphael: Open interface**, **Raphael: Background**, **Raphael: Stop** and **Raphael: Backend tests** under **Terminal → Run Task**. These tasks expect the bundled `engines` folder. A debugger configuration is not included; F5 is not required to run the project.

Change the browser layout in `web/index.html`, styling in `web/styles.css`, web behavior in `web/app.js`, the native orb in `raphael/desktop/orb.py`, and desktop conversation behavior in `raphael/desktop/controller.py`. Stop and restart after Python/configuration changes. Reload the browser after web edits. See [RUN-IN-VS-CODE.md](RUN-IN-VS-CODE.md) for the focused walkthrough.

## Run a GitHub clone or source-only download

The GitHub repository and the small source-only ZIP **exclude** the multi-gigabyte models, bundled runtimes and personal runtime data. Cloning the code alone is not the same as downloading the complete portable package.

The easiest setup is to copy the **`engines` and `models` folders from your full package** into the root of the clone. Keep the repository's `config.toml`, whose bundled paths point there. You can then use the same commands above. Those large folders are ignored by Git. If you already have Git installed:

```powershell
git clone https://github.com/Varshith-eati/RAPHAEL_AI.git
cd RAPHAEL_AI
# Copy engines and models from the complete package into this folder first.
.\Open-Raphael.cmd
```

For an advanced setup without the bundled Python runtime:

1. Install Python 3.12 x64 and Ollama for Windows.
2. Create a virtual environment and install the pinned dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
```

3. Supply the required local model assets. Copy the full package's `models` folder if available. Otherwise, install `llama3.2:latest` and `qwen3.5:4b` through Ollama; provide Kokoro `kokoro-v1.0.onnx` plus `voices-v1.0.bin`; and provide a faster-whisper-compatible **Whisper base directory** containing `model.bin`, `config.json`, `tokenizer.json` and `vocabulary.txt`. Upstream project references are in [THIRD-PARTY.md](THIRD-PARTY.md). Model/library availability and licensing are upstream concerns; the bundled package is the validated offline route.
4. Edit `config.toml` to match your installation. Use `chat.executable = ""` for the separately installed Ollama and `chat.models_dir = "~/.ollama/models"` for its normal local model store. Set the two voice paths and the transcription directory to the assets you actually supplied. These keys belong in their existing `[chat]`, `[voice]` and `[transcription]` sections. Relative paths resolve from `config.toml`.
5. Run `.\Open-Raphael.cmd`, or `.\.venv\Scripts\python.exe -B .\desktop.py --open`.

The launcher prefers a bundled `engines\python` over `.venv` when both exist. The included VS Code tasks target the bundled interpreter; change their command to `${workspaceFolder}/.venv/Scripts/python.exe` if you choose the virtual-environment route. Raphael does not automatically download missing models at runtime.

## Enable or disable Windows startup

1. Start the desktop companion from the **location you intend to keep**.
2. Right-click the Raphael tray icon. Open the Windows tray overflow if the icon is hidden.
3. Turn on **Start with Windows**. The same setting is in native **Background & Real-Time Interaction → General**.
4. Enabling startup also enables **Hey Raphael**, background operation and minimized launch. You can separately disable wake listening afterward.
5. At your next Windows sign-in, Raphael waits **15 seconds by default**, starts silently and initializes local wake recognition. The main window and orb remain hidden until activation. A cold recognition load takes additional time.

No administrator permissions, Task Scheduler editing or manual registry editing are needed. Raphael creates `Raphael Companion.lnk` in your current user's Windows Startup folder. You can inspect that folder with **Win+R → `shell:startup`**. The shortcut stores the application location and config path.

To disable automatic launch, turn off **Start with Windows**. That removes this installation's shortcut; it does not stop the current session. Use **Exit Raphael** to stop it now. Task Manager can also disable Windows startup apps independently. If you move or rename the project folder, disable startup in the old copy, stop it, then enable startup from the new location.

Fresh extractions have startup and wake listening off because the download excludes your settings. A startup registration on your existing laptop points to its existing installation; downloading or extracting another copy does not move that registration.

Crash recovery retries abnormal exits after **5, 15 and 45 seconds**, then stops a repeated failure. Ten stable minutes reset the retry budget. **Recover after a crash** can be disabled in General settings. Intentional Exit remains stopped until you launch Raphael again or sign in next time. User apps opened by Raphael remain open during Raphael's shutdown/recovery.

## Microphone, voice and orb controls

| Control | Result |
| --- | --- |
| `Ctrl+Alt+R` | Activate the floating orb and begin a voice session. |
| `Ctrl+Alt+Esc` | Stop the active session and dismiss the orb. |
| `Ctrl+Alt+M` | Mute the microphone immediately. |
| Tray → Enable Hey Raphael | Monitor local speech for the wake phrase while the main interface is closed. |
| Tray → Pause/Resume listening | Pause or resume monitoring. Activate also resumes a muted session. |
| Tray → Settings → Voice | Choose the microphone, voice, volume and timing. |
| Say “goodbye” or wait | End the conversation and fade out the orb. |

Listening uses cyan microphone-reactive waves, thinking uses violet moving rings, and speaking uses mint waves following output audio. Follow-up listening lasts eight seconds by default and retains recent conversation context. The microphone indicator distinguishes wake monitoring from a live conversation. Wake recognition uses local Whisper on detected utterances, so it is not a dedicated tiny always-on wake model and cannot wake a powered-off or sleeping laptop.

## Testing from your own computer

Run the backend suite without a real microphone or large model inference:

```powershell
.\engines\python\python.exe -E -s -B -m unittest discover -s tests -p "test_*.py" -q
```

Run the native crash-recovery test (it only terminates its own temporary test processes):

```powershell
.\engines\python\python.exe -E -s -B .\tests\desktop-recovery.py
```

Run the native conversation/orb test with fake audio:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\engines\python\python.exe -E -s -B .\tests\desktop-smoke.py
Remove-Item Env:\QT_QPA_PLATFORM
```

For optional browser tests, install Node.js with npm and have Chrome installed. Then:

```powershell
npm install
npm test
npm run test:interface
# For real model/browser suites, use the supplied local models and interpreter:
$env:RAPHAEL_PYTHON = (Resolve-Path .\engines\python\python.exe).Path
node .\tests\microphone-modes.cjs
```

Run integration suites one at a time: they share test ports/hotkeys. The complete package also has **Verify-Package.cmd**, which checks shipped-file hashes. After intentionally editing code, a changed-file warning from that verifier is expected. The GitHub source checkout does not include the portable package's large hash manifest.

Validation before this documentation release: **79 backend tests passed**, along with native orb/startup/recovery tests. A short generated-silence wake sample measured about 0.03% total CPU, 227 MB resident memory and 1.62 GB private memory commitment for the companion, excluding its small supervisor. Real ambient speech increases CPU. These are measurements, not guaranteed hardware requirements. Actual sign-in and physical microphone wake accuracy still need hands-on verification.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Double-clicking Launch-Desktop seems to do nothing | It is intentionally silent. Check the tray/overflow, press `Ctrl+Alt+R`, or run `Open-Raphael.cmd`. |
| No response or port already in use | Exit the other Raphael installation. Only one copy should use ports 8768/11436. Read `runtime/recovery.log` and `runtime/raphael.log`. |
| Python/runtime missing | Extract the entire full ZIP. A GitHub/source-only download needs `engines` or a configured `.venv`. |
| Missing module / import error | Use the bundled interpreter, or install `requirements.lock.txt` into the virtual environment you actually run. |
| Missing chat, voice or recognition model | Check `config.toml` and the `models` directory. The running app never downloads missing models automatically. |
| Wake phrase does not respond | Enable Hey Raphael, unmute, select the correct microphone, allow Windows desktop-app microphone access and wait for recognition readiness. Try the keyboard shortcut to distinguish wake detection from the rest of the conversation. |
| Browser microphone denied | Allow microphone access for the local Raphael site as well as Windows desktop-app microphone access. |
| Speech echoes or interrupts itself | Use headphones. Native interruption recognizes “Raphael, stop”; native capture has no built-in acoustic echo cancellation. |
| No spoken reply | Enable Spoken replies or start a call, check output volume/device, and check the local voice model paths. |
| First response is slow | Local models load on first use. Use the smaller model and close other heavy applications. Streaming does not remove all voice-generation delay. |
| Shortcut does not work | Another program may own it. Use tray Activate or choose another activation shortcut in native settings. |
| Does not start after sign-in | Check Start with Windows, Task Manager startup-app state, the shortcut in `shell:startup`, and whether the project was moved. Allow the configured delay and model load. |
| Source clone does not run like the full ZIP | Git excludes engines and models. Copy those folders from the full package or follow the manual source setup above. |
| PowerShell refuses a downloaded file | Prefer the provided `.cmd` launchers. If Windows marks the ZIP as downloaded, inspect its Properties and unblock it only if you trust this copy. Do not disable system-wide security settings. |

Keep the previous ZIP or folder before upgrading. Stop Raphael before replacing source files or migrating `runtime` settings. Do not mix old/new Python library folders. Keep the upstream dependency/model license notices and [THIRD-PARTY.md](THIRD-PARTY.md) with redistributed dependencies and models.

## Start

- **Launch-Desktop.cmd** starts silently in the system tray, with no main interface or persistent console window. Repeating it keeps the existing background instance. **Open-Raphael.cmd** or **Open Raphael** in the tray opens the existing interface when you want it. Closing the browser leaves the companion available. **Ctrl+Alt+R** activates the floating orb; **Ctrl+Alt+Esc** dismisses it; **Ctrl+Alt+M** mutes the microphone. Choose **Exit Raphael** to stop it completely.
- **Launch-Raphael.cmd** runs the familiar browser-only version. Use **Stop-Raphael.cmd** to stop it. Do not run both versions on the same ports simultaneously.
- In the complete package, Python, Ollama, the speech libraries and all configured models are included under `engines/` and `models/`. Extract the whole folder before running. No separate account or API key is needed.
- A source-only checkout can use `.venv`; supply local models and set their paths in `config.toml`. The full package and GitHub configuration use the `models` folder at the project root.

Windows startup and wake listening are **off by default in fresh settings**. Enable **Start with Windows** in **Connection → Background & Real-Time Interaction → Desktop, wake phrase & startup settings**, or through the tray menu. Enabling startup also enables wake listening and background mode. Wake listening remains separately controllable afterward. Startup uses one current-user Windows Startup shortcut, supports long project paths, and does not require administrator access. Disable startup before moving or deleting the application; launch from the new location and enable it again. Windows Task Manager can independently disable startup apps.

At sign-in Raphael waits the configurable startup delay (15 seconds by default), stays hidden and loads only recognition for wake listening. Chat and voice-generation models load when used. A small supervisor recovers crashes with 5, 15 and 45-second delays, then stops repeated failures. Ten minutes of stable running resets that retry budget. **Recover after a crash** is available in native General settings. An intentional **Exit Raphael**, Stop-Desktop, or Windows session shutdown does not trigger recovery; explicit Restart is handled by the supervisor. Its Windows job object cleans up the owned child-process tree if the companion or supervisor crashes. Recovery logs are bounded in `runtime/recovery.log`.

The default workspace is `Documents\Raphael Workspace`. The complete package creates it for the current Windows user. Your development installation keeps its existing workspace. No personal workspace files, saved profile or chat history are included in release archives.

## Conversation controls

**Spoken replies** switches between written replies and spoken answers. **Read aloud** speaks typed text directly. **Call Raphael** starts a browser voice conversation; the microphone icon records a single message. The previous interface preview, Appearance drawer, Explore the core, memory and laptop panels remain available.

Text now appears as it arrives. Speech starts from complete sentences or short phrases while remaining text is generated. One voice plays at a time; Stop cancels outstanding jobs and prevents late audio from playing. The first phrase is limited to about 72 characters where word boundaries permit. Total spoken text per answer is bounded to 2,400 characters. Longer replies remain visible.

In **Connection → Background & Real-Time Interaction**, you can change text/speech streaming, speech endpoint delay, automatic model routing, performance logging, and **Speak to interrupt**. Save the settings, then start a new call. In browser calls, this interruption option keeps the microphone on during answers and stops the previous turn when speech is detected. Browser echo cancellation is requested; headphones are recommended. Without this opt-in, the microphone remains off during replies and the Interrupt button is available.

The native companion checks for **“Raphael, stop”** during a reply when its interruption setting is enabled. It rejects matching playback text, but PortAudio has no built-in acoustic echo cancellation. This is a local recognition pipeline, not instantaneous full-duplex audio intelligence. Device-specific echo, noise and natural interruptions still need testing on your microphone.

## Wake phrase and background orb

The native tray companion can listen for **“Hey Raphael”** after you enable wake listening. Say the wake phrase followed by a question, or pause after the phrase and then ask. Following a reply, the default listening window is eight seconds. A timeout hides the orb and returns to wake monitoring, or closes the microphone when wake monitoring is off.

The orb has hidden, activating, listening, thinking, speaking and deactivating states. Cyan listening waves respond to the microphone, violet thinking rings rotate faster, and mint speaking waves follow playback amplitude. Audio pulses use a fast attack and gentle release; fades and rotation use elapsed time so different animation quality settings keep a consistent pace. Reduced motion, configurable size/glow, optional dragging, screen-boundary correction and click-through mode are available. No animation timer runs while it is hidden. An orange dot on the tray icon indicates that capture is active; its tooltip distinguishes wake monitoring from conversation capture. Mute and Exit take effect immediately.

On a cold start, the orb says **Preparing microphone** until local recognition and capture are ready; the listening timeout starts after readiness. Failed microphone retries end the conversation instead of leaving a misleading listening indicator. Follow-up questions share the same conversation history without needing another wake phrase. Say **goodbye** or let the listening window expire to fade the orb out.

Wake detection uses local Whisper transcription of detected utterances. It is not a dedicated low-power wake-word model and cannot wake a sleeping or powered-off computer. No raw microphone recording is saved. The browser's existing wake feature still works while that page is open and resets on refresh.

## Performance and models

See **docs/performance-report.md** for measured before/after results and limitations. Warm text reached the target on the tested short workloads. Longer uncached Kokoro speech remained slower than the 0.5–1.5 second target. First requests also pay model-loading cost. Small samples, operating-system caches, answer length and available CPU/RAM affect these numbers.

Standalone general questions use a smaller conversational prompt with the same selected model. Ambiguous questions, local references and action requests keep the full tool protocol. You can disable this fast path in the native Performance settings. Tools and their approval checks remain available.

Choose **Automatic** in the model selector to use the saved model preference or optional routing. Routing is a lightweight keyword rule, not an extra model request: simple questions use the configured fast model and complex requests use the advanced model. An explicit model choice wins. Missing routing models produce an error; there is no silent cloud fallback or downgrade. Switching models can add loading latency.

Recent chat history remains bounded. SQLite stores only the name and notes you explicitly save. Its connection is reused, and cached preferences are invalidated on local saves and changes made through another database connection. The default memory limit retains all 12 saved notes. No embeddings or chat-history database were introduced.

## Laptop access and approvals

Raphael can read system information; open supported apps, Gmail, YouTube, Google, GitHub and File Explorer; and work with text files in the approved workspace. Writes and folder creation require a reviewed proposal and an Approve button. Every outside-workspace listing/read also requires its own approval and remains read-only. Chat, voice, file content and model output cannot approve those requests.

Website opening uses the internet. Raphael does not read inboxes, operate accounts, execute arbitrary shell commands, delete files or install software. See **docs/laptop-access.md** for the existing boundaries.

## Development setup

Use Windows x64 and Python 3.12 to match the validated bundle. Other Python versions have not been validated for this pinned dependency set. Create `.venv` and install `requirements.lock.txt`. Set paths in `config.toml` for the installed local Ollama models, Kokoro ONNX model/voices and Whisper base model. No runtime model downloads occur. Keep interface port 8768 and Ollama port 11436 free, or change both ports for a second installation.

New dependencies are **PySide6-Essentials 6.11.3**, its matching **shiboken6**, and **sounddevice 0.5.6**. The desktop overlay uses Qt Widgets; it does not embed Chromium or WebEngine. Existing browser, Ollama, faster-whisper and Kokoro components are reused. Qt/PortAudio and model licenses must be retained when redistributing binaries; see **THIRD-PARTY.md** in the complete package.

Settings are validated and atomically saved in `runtime/interaction-settings.json`. All defaults and ranges are in `raphael/realtime/settings.py`. Configuration for model files and engine ports remains in `config.toml`. Native desktop API sessions bootstrap through an owner-restricted local IPC connection and browser URL fragment. The browser-only legacy launcher retains its original single-user localhost token bootstrap; do not expose it on a network.

## Test and diagnose

**Run-Tests.cmd** runs backend tests without loading real models. Additional commands and results are documented in **docs/testing-report.md**. Real model browser tests use generated WAV input through Chrome's fake microphone, not your hardware microphone. Run them one at a time because they share test ports.

Optional diagnostics write numeric timings and allowlisted stage names to bounded `runtime/performance.jsonl` files; conversation text and recordings are excluded. `GET /api/performance` reports mean, median, P95 and maximum values. The normal application log records component/error types. There are no automatic model retries that might repeat laptop actions. Audio-device recovery has three bounded retries; Activate or Restart lets you try again afterward.

## Preservation and remaining checks

The earlier source is preserved next to the development folder as `raphael-modular-before-realtime-2026-10-29`. The complete previous package remains `Raphael-Full-Project.zip`. No existing user data was replaced.

See **docs/feature-checklist.md** for implemented and partial features. Physical microphone echo, Windows sign-in startup, sleep/resume, multiple monitors and long-duration stability require manual checks. The automated tests do not certify those hardware experiences. Existing historical reports in `docs/` are versioned evidence; **testing-report.md** identifies which were rerun for 0.6.

See **docs/windows-startup.md** for the 0.6.2 startup, recovery and idle-resource validation, including the remaining real sign-in check.
