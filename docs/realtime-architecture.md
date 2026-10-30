# Real-time and Windows companion upgrade

## Existing architecture (before changes)

Raphael 0.5 is a local Python HTTP application, not a native desktop app.
`server.py` composes the modular backend; `web/` is the existing HTML/CSS/JavaScript interface.
Ollama provides local Llama 3.2 and Qwen 3.5 4B chat. Kokoro ONNX provides English
speech, and faster-whisper base recognizes microphone audio. Three workers keep
inference outside the browser thread. SQLite holds explicitly saved preferences;
conversation history is bounded and held in memory.

The browser's recorder worklet performs energy-based endpointing. The live-call
controller checks transcribed utterances for "Hey Raphael". It requires an open
page and closes the microphone during model generation and playback. There is
no system tray, global shortcut, Windows login entry or native floating window.

Two source-visible latency costs require measurement: laptop-enabled chat waits
for a complete structured model answer, and speech starts only after the full
answer is complete. Profile retrieval is small and bounded; no embeddings or
retrieval database exist, so adding an embedding cache would not help this design.

## Implementation plan

1. Preserve version 0.5 and benchmark equivalent short, normal and reasoning
   requests with separate test data. Record monotonic timings without prompts,
   replies or microphone recordings in performance logs.
2. Stream validated conversational text through the existing local model adapter;
   preserve tool validation and human approvals. Generate bounded sentence-level
   speech while text continues, with one cancellation generation for the turn.
3. Add small reusable settings, timing, routing, speech-buffer and session-state
   modules. Keep the existing browser interface and saved-memory format.
4. Add a native companion using Qt for Python Essentials for the tray/overlay and
   PortAudio through sounddevice for local audio. Do not embed Chromium/WebEngine.
   The companion owns the existing backend and opens its browser UI on request.
5. Add per-user single-instance IPC, a configurable global hotkey and opt-in login
   startup. Wake monitoring and barge-in are explicit settings, off initially.
6. Exercise cancellation, stream ordering, settings, state transitions, startup
   command construction and cleanup with isolated fixtures. Test real model and
   speech paths separately. Report hardware/login/multi-monitor checks honestly
   when they cannot be performed automatically.

## Boundaries and constraints

All inference and wake checks remain local. File writes and outside-workspace
reads retain their existing approval gates. Background settings cannot be
silently enabled by the language model. Closing a browser page must not own or
terminate the native companion's lifetime; Exit Raphael does.

Whisper-based wake detection reuses the existing local model rather than claiming
a dedicated trained wake-word network. Physical speaker echo and real microphone
performance need a hardware trial; synthetic audio alone cannot establish them.
Target response times are goals, not guarantees on this laptop.

The pre-upgrade source is preserved in the neighboring
`raphael-modular-before-realtime-2026-10-29` folder. The complete 0.5 Windows
package and verified ZIP are also preserved as `Raphael-Full-Project`.

## Implemented structure

`raphael/realtime/` contains validated atomic settings, numeric timing statistics,
conservative prompt/model routing and the sentence buffer. `services/jobs.py`
retains one worker per engine and adds lazy startup and timing hooks. The browser
continues to use the existing HTTP API with incremental job snapshots.

`desktop.py` owns one QApplication, the same Application/LocalServer and an
owner-restricted QLocalServer. `desktop/controller.py` owns session/cancellation
state, `audio.py` owns bounded PortAudio capture/playback, `orb.py` paints the
native overlay, `settings_dialog.py` exposes the settings model, and `windows.py`
owns current-user startup, mutex and global shortcuts. UI actions cross threads
through Qt signals. Model inference stays in the existing engine workers.

No WebEngine, cloud provider, general command executor, embedding service or
new chat-history database was introduced. The ordinary browser-only launcher
remains supported. The full tool prompt was retained after a compact version
failed a real file-action test. General standalone conversation uses the same
model with a smaller prompt; uncertain/action requests retain all tool schemas.

## Earlier security review context

Before the implementation phase, the supplied security-audit skill was applied
as ten focused source reviews: HTTP/bootstrap; storage/audio/logging; resource
bounds; workspace paths; outside-file approvals; app launches; AI/tool boundaries;
frontend rendering; microphone/call lifecycle; packaging/dependencies.
Those were source inspections, not reproduced exploit tests or certification.
Review candidates needing isolated validation included cross-account localhost
bootstrap, path replacement races in a lower-trust shared folder, and induced
allowlisted app launches from untrusted model context. The desktop's private
bootstrap narrows the first issue for that launch mode. The browser-only legacy
mode and the other hypotheses are not claimed to be comprehensively resolved.
