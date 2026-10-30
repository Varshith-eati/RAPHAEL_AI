# Raphael validation — 29–30 October 2026

## Windows startup update (0.6.2)

All **79 backend tests** pass, including temporary Windows shortcut roundtrips, bounded recovery policy checks, and a real process-tree test proving user-opened apps survive Raphael cleanup. The expanded native smoke test passes startup enable/disable and save-failure rollback, in addition to existing conversation/orb behavior. Real process tests verify hidden startup, single instance, forced-crash recovery, stop during backoff, disabled recovery and clean exit. The real local recognizer is ready in a generated-silence idle probe while chat/TTS stay sleeping. See `windows-startup.md`, `startup-recovery-results.json` and `startup-idle-results.json` for evidence and limitations. Actual sign-in and physical microphone wake accuracy remain manual checks.

## Previous conversation upgrade (0.6.0–0.6.1)

On 30 October, interrupted-question/partial-answer retention was added and verified
in browser and native session tests. All 73 backend tests passed again. Existing
latency measurements below remain the 29 October measurements; this context fix
does not change the model or speech inference path.

## Executed and passed

| Check | Evidence and limits |
| --- | --- |
| 73 Python regression tests | `python -B -m unittest discover -s tests -p 'test_*.py' -q`: configuration, memory, HTTP boundaries, audio validation, queues, cancellation, laptop approvals and 14 new streaming/routing/settings/audio checks. Fake inference; real temporary files/HTTP. |
| Streaming speech orchestration | `node tests/voice-stream-unit.cjs`: speech starts before final text, ordered once-only playback, delayed-job cancellation, bounded text. Simulated WebAudio/provider responses. |
| Live-call state and barge-in | `node tests/live-call-unit.cjs`: VAD, wake gating, endpoint, silence bounds, manual interruption, natural speech interruption without discarding the new recording, late reply/permission races. Simulated devices. |
| Existing interface | `node tests/interface-regression.cjs`: compact design, context trimming, persistence, audio-unavailable text fallback, late microphone permission, no browser exceptions. Intercepted API responses. |
| Real text, voice and speech-to-speech | `node tests/microphone-modes.cjs`: real Llama, Kokoro and Whisper; direct read aloud; cancellation; no external requests; phone/tablet layouts. Generated WAV through Chrome fake microphone. `microphone-test-results.json`. |
| Real wake and follow-up calls | `node tests/live-call-browser.cjs`: consecutive hands-free turns, “Hey Raphael” plus question, wake-only greeting, unrelated speech rejection, mute/resume, manual interruption and responsive call bar. Generated WAV input. `live-call-test-results.json`. |
| Approval interface | `node tests/laptop-browser.cjs`: exact reviewed writes, reject, inert previews, approved outside reads and access disable. Fake model; real HTTP/file implementation. `laptop-browser-results.json`. |
| Real laptop actions | `python tests/laptop-real.py llama3.2:latest`: actual system information, isolated reviewed text-file creation, reading the test file. `laptop-real-results.json`. |
| Real app/website routing | `python tests/expanded-real.py`: six app/website targets, external listing/read proposals. Native app launches mocked; generated approvals affect only isolated test data. `expanded-access-real-results.json`. |
| Native orb/settings/session | `QT_QPA_PLATFORM=offscreen python tests/desktop-smoke.py`: hidden idle, lazy workers, all settings controls, rendered orb/settings, speech/follow-up transitions, timeout/mute/exit. Audio and engines simulated. `desktop-test-results.json`. |
| Real Windows process lifecycle | `python tests/desktop-process.py`: hidden launch, private bootstrap, second-instance IPC, explicit process exit, unchanged startup registration. No microphone/model startup. `desktop-process-results.json`. |
| Before/after local latency | Three workload categories, three trials each; full methodology, failures and cache caveats in `performance-report.md`. |
| Self-contained release | 73 backend tests passed under bundled Python. Bundled Ollama found both copied models; Kokoro generated speech; Whisper transcribed it; Llama answered correctly. Bundled Qt passed both desktop lifecycle suites. `packaged-runtime-results.json`; the full folder also has `full-package-verification.json`. |

## Failures found and addressed

- The shortened tool definition prompt made Llama choose folder creation for a requested text file. Full original definitions were restored for tool requests; both real tool suites then passed. Smaller prompts apply to conservative standalone conversation.
- Persistent SQLite connections exposed missing test cleanup and failed-initialization cleanup. Connections now close explicitly, on failed initialization, and for short-lived repository callers. Concurrent/profile-deletion tests pass.
- An oversized HTTP test encountered a Windows reset with unread bytes. Small oversized bodies now drain within a bounded limit before returning 413; regression tests pass.
- Earlier browser assertions assumed one speech request per complete answer. They now check the first streamed phrase; separate orchestration tests verify complete phrase order and cancellation.
- Qt's offscreen plugin did not enumerate Windows text fonts. The companion loads the installed Segoe UI font when needed; rendered previews were checked afterward.

Initial restricted test execution could not create localhost connections/hardlinks. Those checks were rerun with the required local execution permissions. Error messages from deliberate failure fixtures are expected; final suite status is the pass/fail evidence.

## Not executed on physical hardware

- Spoken interruption using the actual microphone while speakers play; acoustic echo/noisy-room quality.
- Actual Windows sign-out/sign-in startup, Task Manager startup-disable behavior, and moving the installed folder while enabled.
- Physical microphone/speaker disconnection, sleep/resume, fullscreen overlays, multiple monitors and high-DPI changes.
- Long-duration soak, memory/GPU profiling over hours, and a clean second Windows machine.
- Comprehensive output-quality evaluation or a statistically reliable P95 latency study.

## Manual acceptance checklist

1. Start `Launch-Desktop.cmd`. Verify it stays in the tray without opening a browser. Run it again; there must still be one companion and no browser. Use `Open-Raphael.cmd` to open the main interface; closing that tab must leave the tray running.
2. Activate with Ctrl+Alt+R. Check that capture is indicated. Speak, hear a reply, ask a follow-up within eight seconds, then wait for standby.
3. Enable wake listening yourself. Say “Hey Raphael” followed by a question. Check that unrelated speech is ignored. Mute with Ctrl+Alt+M and verify the tray capture dot disappears.
4. Try browser Speak to interrupt with headphones first. During a long answer, say a new instruction; confirm old audio stops and never resumes. Test speakers separately for echo. In the native companion use “Raphael, stop” followed by the new instruction.
5. Enable Windows startup yourself, sign out/in and verify only one hidden instance. Disable startup afterward if unwanted. Exit must stop the process without relaunching.
6. Move the orb between displays with dragging enabled, change scaling, disconnect a display, then try reduced motion/fullscreen apps.
7. Disconnect and reconnect the audio device; confirm bounded retry and manual Activate recovery. Put Windows to sleep mid-reply; confirm no stale playback on resume.

Run real-inference/browser suites sequentially: they share test ports. Reports with older versions/timestamps in this directory are historical evidence, not reruns for 0.6.
