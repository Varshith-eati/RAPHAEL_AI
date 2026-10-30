# Upgrade feature checklist

## Implemented and exercised

- Incremental text, conservative smaller-prompt path, preserved tool schema and human approval flow.
- Phrase-based speech synthesis during text generation, bounded prefetch, ordered playback and cancellation of stale work.
- Segment transcription, configurable VAD/endpoint, lower client polling overhead; existing local INT8/greedy Whisper retained.
- Cached saved preferences with cross-connection invalidation, bounded conversation context and configurable note count.
- Explicit-preference model routing without an extra model call; no cloud fallback or silent downgrade.
- Content-free timing diagnostics and before/after benchmark report with cache/cold-start limitations.
- Opt-in browser speech interruption with browser echo cancellation requested; manual interrupt remains available.
- Optional native tray companion, transparent cyan audio-reactive orb, six explicit visual states, hidden idle with no paint timer, eight-second follow-up, mute/dismiss/exit.
- Persistent validated native General/Voice/Orb/Performance settings; browser streaming/interruption controls.
- Current-user startup registration code, optional delay, single-instance mutex plus owner-restricted IPC and private desktop token bootstrap.
- Lazy engine startup, bounded microphone reconnection, sleep-gap cancellation, explicit restart/exit cleanup.
- Previous version preserved; new source and full Windows release folders kept separate.

## Partial or hardware-dependent

- The text target was reached on measured warm standalone workloads. Fresh longer speech remains above the 0.5–1.5 second first-audio target. Cold model loading is slower. This is not a native end-to-end audio model.
- Wake detection reuses Whisper on utterances; it is not a dedicated low-power wake network. Recognition pauses while a detected phrase is being processed.
- Browser barge-in is VAD-driven and depends on browser/device echo cancellation. Native barge-in recognizes a named stop command and has no built-in AEC. Neither has been acoustically validated on the physical microphone.
- Phrase prefetch avoids overlap; a slow CPU may still create gaps when synthesis falls behind playback.
- DPI, multi-monitor bounds, drag and resume handling are implemented. Their physical configurations remain untested. Always-on-top overlays are not guaranteed over exclusive fullscreen applications.
- Background-disabled browser close is detected with an authenticated heartbeat and a short timeout; it is not an embedded native main window.
- Startup enable/disable code is provided. Actual sign-in and Task Manager startup behavior require the manual acceptance test. The test suite does not silently register startup.
- Recovery retries audio-device opening three times with backoff. Failed model initialization requires user restart; actions are never automatically retried.

## Pending further work

- A dedicated wake-word model and robust native acoustic echo cancellation.
- Additional CPU/GPU speech inference tuning or a smaller voice model, measured with pronunciation/voice-quality comparison.
- Hardware/soak/clean-machine validation, broad reasoning-quality tests and larger latency samples.
- A signed installer/updater. The delivered folder is portable source plus local runtimes/models.
- Live web research, account operation, arbitrary shell control and reminders remain outside existing supported capabilities.
