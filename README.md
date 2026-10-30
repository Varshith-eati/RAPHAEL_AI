<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:090B1A,45:34206B,100:00D9FF&height=220&section=header&text=RAPHAEL%20AI&fontSize=58&fontColor=FFFFFF&fontAlignY=38&desc=Your%20local-first%20AI%20desktop%20companion&descAlignY=60&descSize=18" alt="Raphael AI banner" width="100%" />

<br/>

### ◈ A little intelligence. A little magic. Right on your desktop.

**Local AI · Real-time voice · Floating orb · Windows companion**

<br/>

[![Platform](https://img.shields.io/badge/Platform-Windows%20x64-34206B?style=for-the-badge&logo=windows&logoColor=white)](#-requirements)
[![AI](https://img.shields.io/badge/AI-Local--First-00BFA6?style=for-the-badge&logo=ollama&logoColor=white)](#-privacy--control)
[![Interface](https://img.shields.io/badge/Interface-Web%20%2B%20Desktop-00AEEF?style=for-the-badge&logo=html5&logoColor=white)](#-what-is-raphael)

<br/>

[🚀 Get Started](HOW%20TO%20SETUP.md) · [🧑‍💻 VS Code Guide](RUN-IN-VS-CODE.md) · [🧪 Testing](docs/testing-report.md) · [📜 Third-Party Notices](THIRD-PARTY.md)

</div>

---

## ◈ What is Raphael?

**Raphael is a local-first personal AI assistant for Windows** that brings conversational AI, voice interaction, and a floating desktop companion together in one experience.

Chat with it, talk to it, summon its orb, and use supported laptop tools—with approvals for actions that change files.

<table>
<tr>
<td width="50%" valign="top">

### 🧠 Local conversations
Chat using configured local language models, without requiring a cloud AI API key.

### 🎙️ Voice interaction
Use local speech recognition and spoken responses to interact hands-free.

### 🔮 Floating orb
A native desktop orb animates through listening, thinking, and speaking states.

</td>
<td width="50%" valign="top">

### 👋 “Hey Raphael”
Optionally enable local wake-phrase listening while the main interface is closed.

### 🖥️ Windows companion
Run in the background, use keyboard shortcuts, and optionally start with Windows.

### 🛡️ Approved laptop tools
Open supported apps and websites, inspect system information, and work with files within defined permission boundaries.

</td>
</tr>
</table>

## ✨ See the experience

<div align="center">

| 🎧 Listening | 🧠 Thinking | 🗣️ Speaking |
|:---:|:---:|:---:|
| Cyan microphone-reactive waves | Violet moving rings | Mint audio-reactive waves |

*The floating orb changes its animation to reflect Raphael's current interaction state.*

</div>

## 🚀 Get started

### The easiest way: use the complete portable package

> **Important:** The complete portable ZIP and the GitHub source repository are different. The source repository does not include the large `engines/` runtime and `models/` folders.

**1. Download and extract**

Extract the entire complete ZIP into a normal folder, for example `C:\Raphael`. Do not run it inside the ZIP viewer or extract it into `Program Files`.

**2. Open the project folder**

Open the extracted folder containing `desktop.py`, `config.toml`, `engines/`, `models/`, and `web/`.

**3. Launch Raphael**

| Want to… | Run this |
|---|---|
| Open Raphael and its interface | `Open-Raphael.cmd` |
| Start quietly in the system tray | `Launch-Desktop.cmd` |
| Stop the desktop companion | `Stop-Desktop.cmd` |
| Run browser-only mode | `Launch-Raphael.cmd` |
| Stop browser-only mode | `Stop-Raphael.cmd` |

**4. Ask your first question**

Start with a typed message. The first model load can take longer than later replies.

<div align="center">

### 📘 Need the full walkthrough?

**[Open HOW TO SETUP.md →](HOW%20TO%20SETUP.md)**

</div>

## ⌨️ Keyboard shortcuts

| Shortcut | Action |
|:---|:---|
| `Ctrl + Alt + R` | Activate the floating orb and begin a voice session |
| `Ctrl + Alt + Esc` | Stop the active session and dismiss the orb |
| `Ctrl + Alt + M` | Mute the microphone immediately |

To use the wake phrase, enable **Hey Raphael** from the tray menu or settings. Wake recognition uses local Whisper transcription; it is not a tiny dedicated wake-word model and cannot wake a sleeping or powered-off computer.

## 💻 Requirements

| Component | Recommended / supported |
|---|---|
| OS | Windows x64; Windows 11 was used for validation |
| RAM | 16 GB is a practical recommendation |
| Storage | About 8.1 GB for the complete ZIP, 9.7 GB extracted; allow around 25 GB free for setup and updates |
| Browser | Chrome or Edge |
| Microphone | Needed for voice input; not needed for typed chat |
| VS Code | Optional |
| Node.js + npm | Optional; used for browser tests |

The complete portable package includes Python 3.12.14 x64, Ollama, pinned Python dependencies, and configured local chat, transcription, and voice assets. With that package, you do not need to separately install Python, Ollama, Java, Node.js/npm, or obtain an API subscription just to run Raphael.

## 🧑‍💻 Developer corner

### Open in VS Code

1. Open the project folder containing `desktop.py`.
2. Open a PowerShell terminal.
3. Run:

```powershell
.\Open-Raphael.cmd
```

To launch silently:

```powershell
.\Launch-Desktop.cmd
```

To stop:

```powershell
.\Stop-Desktop.cmd
```

### Run tests

With the complete package:

```powershell
.\Run-Tests.cmd
```

Optional browser tests require Node.js/npm and Chrome:

```powershell
npm install
npm test
npm run test:interface
```

See [`docs/testing-report.md`](docs/testing-report.md) for more test commands and limitations. Automated tests do not replace hands-on checks with a real microphone, Windows sign-in, sleep/resume, multiple monitors, and long-duration use.

### Key project files

```text
RAPHAEL_AI/
├── docs/                 # Guides, reports, and feature documentation
├── raphael/              # Assistant and desktop companion components
├── tests/                # Backend, desktop, and integration tests
├── web/                  # Browser interface
├── desktop.py            # Desktop companion entry point
├── server.py             # Backend server
├── config.toml           # Model and runtime configuration
├── requirements.lock.txt # Pinned Python dependencies
├── HOW TO SETUP.md       # Detailed setup guide
└── README.md             # Project overview
```

The complete portable package also contains `engines/` and `models/`. These large folders are intentionally excluded from the source repository.

## 🛡️ Privacy & control

Raphael is designed to run chat, transcription, and voice models locally. Opening websites requires an internet connection.

- File writes and folder creation require a reviewed proposal and an explicit **Approve** action.
- Reads and listings outside the approved workspace require approval and remain read-only.
- Raphael does not read inboxes, operate accounts, execute arbitrary shell commands, delete files, or install software.
- Raw microphone recordings are not saved by the local wake-detection pipeline.
- Do not expose the browser-only localhost interface to a network.

Read [`docs/laptop-access.md`](docs/laptop-access.md) for the detailed permission boundaries.

## 🧰 Troubleshooting at a glance

<details>
<summary><strong>Raphael seems to do nothing when I launch it</strong></summary>

`Launch-Desktop.cmd` is intentionally silent. Check the Windows notification area and its overflow, press `Ctrl + Alt + R`, or run `Open-Raphael.cmd`.
</details>

<details>
<summary><strong>The port is already in use</strong></summary>

Exit other Raphael instances. The default interface port is `8768` and the local model port is `11436`.
</details>

<details>
<summary><strong>A model or Python runtime is missing</strong></summary>

Extract the complete portable package, or follow the source-only setup instructions. Check `config.toml` and the `models/` folder. Raphael does not automatically download missing models at runtime.
</details>

<details>
<summary><strong>Voice or wake phrase is not working</strong></summary>

Check Windows microphone permissions, the selected input device, mute state, local model paths, and whether wake listening is enabled. Headphones can help reduce echo.
</details>

<details>
<summary><strong>Raphael stopped launching after I moved the folder</strong></summary>

Disable startup in the old installation, stop Raphael, launch from the new location, and enable startup again.
</details>

**More help:** [Full setup and troubleshooting guide](HOW%20TO%20SETUP.md)

## 📚 Documentation

| Guide | What's inside |
|---|---|
| [HOW TO SETUP.md](HOW%20TO%20SETUP.md) | Installation, configuration, startup, voice, tests, troubleshooting |
| [RUN-IN-VS-CODE.md](RUN-IN-VS-CODE.md) | Developer workflow in VS Code |
| [`docs/laptop-access.md`](docs/laptop-access.md) | Laptop tool permissions and boundaries |
| [`docs/performance-report.md`](docs/performance-report.md) | Performance measurements and limitations |
| [`docs/windows-startup.md`](docs/windows-startup.md) | Windows startup and crash recovery |
| [`docs/feature-checklist.md`](docs/feature-checklist.md) | Implemented and partial features |
| [`docs/testing-report.md`](docs/testing-report.md) | Test commands and evidence |
| [THIRD-PARTY.md](THIRD-PARTY.md) | Dependency and model notices |

## ⚠️ Before upgrading

- Keep a backup of the previous package or folder.
- Stop Raphael before replacing source files or migrating runtime settings.
- Do not mix old and new Python library folders.
- Retain upstream dependency and model license notices when redistributing components.
- Raphael is a portable Windows application, not a signed installer or Windows service.

---

<div align="center">

### ◈ RAPHAEL AI

*Your desktop. Your models. Your companion.*

<sub>Built for local-first AI interaction on Windows.</sub>

</div>
