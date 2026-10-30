# Background desktop update — 0.6.1, 30 October 2026

Run **Launch-Desktop.cmd**. Raphael starts in the Windows notification area without opening its main interface. If the icon is hidden, open the Windows tray overflow. **Open-Raphael.cmd** opens the existing interface through the running companion. Repeated background launches leave the same instance running silently.

Press **Ctrl+Alt+R** to summon the floating orb above normal desktop windows. Right-click the tray icon and enable **Hey Raphael** to use the local wake phrase instead. Wake capture remains off until you enable it. **Start with Windows** is a separate opt-in tray setting.

- **Listening:** cyan rings and microphone-driven waves.
- **Thinking:** violet rings with faster counter-rotation.
- **Speaking:** mint waves driven by actual output audio amplitude.
- **After a reply:** speak another question during the eight-second follow-up window; no wake phrase is needed. The session retains its recent conversation context.
- **End:** say “goodbye”, press Ctrl+Alt+Esc, or let the listening window expire. The orb fades out while the tray remains running. Wake monitoring continues only if enabled.
- **Microphone:** Ctrl+Alt+M mutes immediately. Activate Raphael or choose Resume listening to resume. Choose the input device and timing in tray settings.
- **Exit Raphael:** stops the companion, audio, hotkeys and local backend. Closing the browser alone does not stop the default background mode.

The listening countdown starts after microphone readiness, so cold model loading does not consume it. Loading is labelled honestly, recognition failures end the session with a recovery message, and repeated activation resets device retry delays. Audio pulses have smooth attack/release. Fade timing is independent of frame rate; the hidden orb does no animation work. Re-enabling a visible orb resumes its animation.

Existing browser chat, speech, memory, local tools, approval checks and interfaces are preserved. Models and dependencies are unchanged. A source backup is in `work/desktop-before-background-2026-10-30` beside the project outputs; the previously delivered ZIP files remain unchanged.

Validation: 73 backend tests; native Windows process/single-instance/exit test; offscreen Qt tests for cold recognition, wake dispatch, two-turn context, audio smoothing, mute, fade, settings and failures. These use simulated microphone/speaker input, not a person speaking into this laptop. Real microphone wake accuracy, speaker echo, Windows sign-in and multi-monitor behavior still need hands-on verification. The overlay is intended for the signed-in desktop, not the Windows lock screen or exclusive full-screen games. Wake recognition uses local utterance transcription and cannot wake a sleeping computer.
