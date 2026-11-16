# Raphael AI | High-Level Design

**Release 0.6.2 · Windows x64 · System architecture**

Raphael runs a conversation on one Windows laptop. A person can type in the browser or summon a floating orb with a shortcut or wake phrase. Both interfaces use the same local chat, speech and laptop services. The desktop companion owns the background session, so closing a browser tab leaves wake listening available when enabled.

## Components and boundaries

| Component | Responsibility |
| --- | --- |
| Browser interface | Captures typed or spoken input, displays incremental replies, plays speech and presents file proposals for review. |
| Desktop companion | Owns the tray, microphone, hotkeys, floating orb and follow-up conversation. Qt signals deliver state changes to the interface thread. |
| Application and local API | Compose the shared services, validate browser requests and expose jobs, settings and profile data on loopback. |
| Inference workers | A separate worker serves each of chat, recognition and synthesis. Ollama serves local Llama or Qwen models, faster-whisper transcribes audio and Kokoro produces speech. |
| Laptop tools | Map supported actions to Windows operations. Enforce workspace boundaries and obtain a human decision when an action needs approval. |
| Windows supervisor | Starts the companion, prevents duplicate background instances and recovers from abnormal exits with bounded retries. |

## A spoken turn

1. “Hey Raphael,” the activation shortcut or the tray starts a desktop conversation. The orb shows listening and responds to microphone amplitude.
2. A pause ends the utterance. Local recognition produces a transcript. The controller adds it to recent conversation context and requests a chat reply.
3. The chat worker publishes text as it arrives. While generation continues, the client can submit complete phrases to the speech worker. A single playback stream keeps phrases in order.
4. The orb responds to playback amplitude while speaking. When playback finishes, the companion opens a follow-up window. A goodbye or timeout hides the orb and returns the companion to its configured idle mode.

A typed turn starts directly at the chat service. A browser call uses the page’s microphone and playback controls. The browser reads growing job snapshots from the local API.

## Data and permissions

| Data | Lifetime and access |
| --- | --- |
| Microphone audio and recent conversation | Audio is processed locally. Recent turns are bounded and kept in memory. |
| Explicitly saved name and notes | Stored in SQLite. The user can replace or clear the profile. |
| Interaction settings | Saved locally and restored across sessions. Model paths and engine configuration live in `config.toml`. |
| User files | The default folder is `Documents\Raphael Workspace`. Workspace writes and folder creation require approval. Each listing or read outside it requires a separate decision. |
| Diagnostics | Optional timing logs contain numeric measurements and stage names. |

The browser connects to the local API on port 8768 by default. The desktop launcher establishes a private session through local IPC. Ollama runs on a separate loopback port, 11436 by default. Opening a supported website is an explicit online action.

## Deployment and tradeoffs

The portable Windows distribution includes engines and models. A source checkout requires those assets separately. On sign-in, the optional startup shortcut starts the companion hidden. The recognition engine can prepare for wake listening while chat and synthesis load on demand. This saves idle resources and increases first-use latency. Wake detection reuses Whisper on detected utterances, so it still incurs recognition work when nearby speech is detected.

The recorded warm normal workload reached a median of 0.147 seconds to first backend text and 5.138 seconds to first available WAV. Those timings exclude physical microphone and speaker latency. Physical-device and Windows sign-in checks remain part of release validation.

**References** · [Architecture](https://github.com/Varshith-eati/RAPHAEL_AI/blob/73930aa36fe525fdf24626fd452b9114459d1e6d/docs/realtime-architecture.md) · [Startup and recovery](https://github.com/Varshith-eati/RAPHAEL_AI/blob/73930aa36fe525fdf24626fd452b9114459d1e6d/docs/windows-startup.md) · [Performance measurements](https://github.com/Varshith-eati/RAPHAEL_AI/blob/73930aa36fe525fdf24626fd452b9114459d1e6d/docs/performance-report.md)
