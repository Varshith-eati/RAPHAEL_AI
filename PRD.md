# Raphael AI | Product Requirements

**Release 0.6.2 · Personal Windows assistant**

## User and outcome

A Windows laptop owner wants to ask a question while working in another app, hear an answer and continue the conversation without repeatedly opening a chat window. They also want to choose when the microphone listens and review actions that expose or change their files.

The product supports two main journeys. At a desk, the user types a question and chooses whether to hear the reply. While working in another window, the user summons Raphael, asks a spoken question, follows up and dismisses the orb. Local models support both journeys offline after setup.

## Functional requirements and acceptance criteria

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| R1 | Typed conversation | A typed question produces a readable reply that appears progressively. The user can stop it or turn spoken replies on. |
| R2 | Voice input and output | The user can dictate one message, start a voice call or read typed text aloud. A silent capture leaves the conversation unchanged. |
| R3 | Hands-free activation | With wake listening enabled and the laptop awake, “Hey Raphael” starts a session. The global shortcut can also activate the orb while the main interface is closed. |
| R4 | Orb and follow-ups | Listening reacts to microphone audio, thinking has its own animation and speaking follows playback. A follow-up within the configured window retains recent context. Goodbye or timeout dismisses the orb. |
| R5 | Microphone and interruption controls | The user can see capture status, mute immediately and stop playback. With native interruption enabled, “Raphael, stop” cancels the current reply. |
| R6 | Background operation | The tray can open the interface, activate the orb, control listening and exit. Closing the browser leaves the desktop companion available. Repeated launches reuse the active instance. |
| R7 | Startup and recovery | The user can enable or disable launch at Windows sign-in. When enabled, the companion starts hidden. A crash triggers bounded recovery and an intentional exit stays stopped for that session. |
| R8 | User-controlled memory | Saving a name or note makes it available in later sessions. The user can clear saved information. Ordinary conversation stays in bounded session memory. |
| R9 | Laptop actions and approvals | Supported apps and websites can open on request. A workspace write or new folder requires approval. An outside-workspace read or listing requires its own approval. Rejecting the proposal leaves the operation unperformed. |
| R10 | Portable setup | On supported Windows x64 hardware, the full package launches after extraction with its bundled runtimes and local models. The setup guide covers VS Code, microphone permissions and startup. |

## Performance and privacy requirements

Aim for 0.5–1.5 seconds to first response where feasible. Evaluate typed and spoken turns separately. For typed turns, measure both the first available text and its appearance on screen. For spoken turns, measure from the end of the user’s speech to audible playback. Report warm and cold model results separately.

Chat, recognition, speech synthesis and wake detection must run locally. Wake listening and automatic startup must be user-controlled. Keep raw microphone recordings out of persistent storage and keep prompts and replies out of timing logs. Restrict laptop actions to supported operations and show the target before requesting file approval.

## Release evidence and open checks

| Area | Evidence for 0.6.2 | Remaining acceptance work |
| --- | --- | --- |
| Text and voice latency | On the recorded warm normal workload, median backend time to first text was 0.147 s. Median time to first available WAV was 5.138 s. | Measure rendered text and physical speaker onset on target laptops. Longer spoken replies remain above target. |
| Conversation and privacy controls | Backend, native and browser checks cover job behavior, orb transitions, cancellation and approval paths. Browser audio tests used generated input. | Exercise wake recognition and interruption with a physical microphone in quiet and noisy rooms. |
| Windows lifecycle | Automated checks cover startup shortcut handling and recovery after a forced companion crash. | Verify actual sign-in, sleep/resume, multiple monitors and extended idle operation on the target system. |

**Scope boundary.** Opening Gmail or GitHub opens the website in the user’s browser. Account operation, arbitrary command execution, software installation and file deletion are outside the supported assistant tools.

**References** · [Feature checklist](https://github.com/Varshith-eati/RAPHAEL_AI/blob/73930aa36fe525fdf24626fd452b9114459d1e6d/docs/feature-checklist.md) · [Testing report](https://github.com/Varshith-eati/RAPHAEL_AI/blob/73930aa36fe525fdf24626fd452b9114459d1e6d/docs/testing-report.md) · [Performance evidence](https://github.com/Varshith-eati/RAPHAEL_AI/blob/73930aa36fe525fdf24626fd452b9114459d1e6d/docs/performance-report.md) · [Windows lifecycle checks](https://github.com/Varshith-eati/RAPHAEL_AI/blob/73930aa36fe525fdf24626fd452b9114459d1e6d/docs/windows-startup.md)
