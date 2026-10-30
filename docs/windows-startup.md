# Windows sign-in startup — Raphael 0.6.2

Enable **Start with Windows** in the tray or native General settings. This also enables local **Hey Raphael**, keeps the assistant in the background and selects minimized launch. After sign-in the companion stays hidden, waits the startup delay (default 15 seconds), then initializes recognition and microphone capture. The main interface and orb stay hidden until you activate Raphael. The tray tooltip and orange dot show microphone activity. Wake listening can subsequently be disabled or muted independently; startup never silently re-enables a saved wake-off preference on each boot.

Disable **Start with Windows** to remove this installation's automatic launch. This does not interrupt the current conversation; **Exit Raphael** or **Stop-Desktop.cmd** stops the running instance. Windows may separately disable startup apps in Task Manager. Use that control if the shortcut exists but Windows does not launch it. The assistant works in the signed-in desktop; it cannot wake a sleeping laptop.

## Implementation

- A per-user `Raphael Companion.lnk` in the Windows Startup folder launches the bundled `pythonw.exe`, the absolute desktop entry point and the selected config. Working directory and arguments are stored separately. Long paths and spaces are supported. Shortcut creation uses fixed PowerShell source with values supplied as JSON, not interpolated commands.
- The earlier HKCU Run entry is migrated only when it matches this installation. Merely launching a different project copy never steals or rewrites another copy's startup registration. Failed settings saves restore the previous shortcut and legacy registration.
- A supervisor mutex and a desktop mutex prevent simultaneous duplicate launches. The existing owner-only IPC still opens the interface or requests graceful shutdown. A repeated silent launch leaves the existing instance untouched.
- The supervisor imports no Qt or model libraries. It waits on a Windows event between process checks. Windows Job Object ownership includes the desktop process and internal descendants, including an Ollama instance started by Raphael. User-opened apps and browser windows explicitly launch outside that job so they remain open after Exit or a crash. It does not attach to or kill a separately running Ollama service. A real helper-process test verifies this separation without opening or closing personal applications.
- An abnormal exit gets at most three recovery attempts, delayed 5/15/45 seconds. Ten stable minutes reset the budget. Intentional Exit is exit code zero; explicit Restart uses a distinct code. Stop can cancel a recovery wait immediately. Graceful shutdown is attempted first; an unresponsive owned process tree is terminated after a bounded timeout.
- Startup failures stay silent and appear in local logs. A repeatedly failing startup eventually stops instead of creating an endless crash loop. Settings include an Enable/Disable recovery toggle. Restart from the tray or launcher starts a new recovery budget.
- Local voice activity detection gates Whisper: silence creates no transcription jobs. The idle wake poll interval is 160 ms; microphone-off idle uses 1 second. The hidden orb's paint timer stays stopped. Chat and Kokoro are lazy. The existing speech-triggered Whisper wake recognizer is retained; no new models, cloud services or recordings are introduced.

## Validation on 30 October 2026

- Automated Windows shortcut creation, reading, enable/disable, ownership, paths with spaces, and rollback were tested in a temporary Startup folder.
- Native sign-in-style launch (`--startup --background`) showed no visible main window or orb, including during its startup delay. Duplicate launch kept the same native process.
- A test-owned native desktop was deliberately terminated; the supervisor restarted it hidden after backoff and the protected local backend returned. A second crash followed by Stop during backoff did not relaunch. Turning recovery off prevented a restart after another crash.
- Existing desktop conversation, settings, audio-state, follow-up, mute, fade and clean-exit tests remain available. Backend regression tests include the new startup checks.
- The idle probe loaded the actual local Whisper base model and fed generated silence through the real endpoint detector. Recognition became ready; chat and voice stayed sleeping, the orb stayed hidden and no transcription jobs were created.

The 10-second development-runtime sample measured 0.02% whole-machine CPU and 93.1 MB working set for the microphone-off companion plus supervisor. The wake-ready companion alone measured 0.03% whole-machine CPU, 226.5 MB working set and 1,621.6 MB committed private memory. Resident memory is not the full memory commitment. These are short samples, not guarantees; real room speech invokes recognition and increases CPU. Wake sampling excludes the small supervisor and uses simulated capture, so it does not establish hardware microphone accuracy or driver overhead. A dedicated small wake-word model would be needed to reduce recognition memory substantially.

Raw results: `startup-recovery-results.json` and `startup-idle-results.json`. Run `tests/desktop-recovery.py`, `tests/desktop-idle.py`, `tests/desktop-process.py` and `tests/desktop-smoke.py` with the project's Python runtime. Use `QT_QPA_PLATFORM=offscreen` for the smoke test. The idle probe never opens a physical microphone. Do not run multiple audio/UI integration tests at once because they share hotkeys.

An actual sign-out/sign-in or reboot, physical microphone wake accuracy, laptop sleep/resume and prolonged room-noise behavior remain manual checks. No reboot or sign-out was performed automatically. Previous project ZIPs and code backups are retained.
