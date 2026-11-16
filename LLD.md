# Raphael AI | Low-Level Design

**Release 0.6.2 · Modules, interfaces and state**

## Module ownership

| Module | Implementation responsibility |
| --- | --- |
| `raphael/application.py` | `Application` composes configuration, storage, services and jobs for both launch modes. |
| `raphael/http_api.py` and `validation.py` | `LocalServer` and its handler enforce request boundaries. Validation converts supported payloads into internal requests. |
| `raphael/contracts.py` | Defines messages, profile, chat/speech/transcription requests, results and cancellation. |
| `raphael/services/jobs.py` | `JobManager` owns job records, per-engine queues, worker threads and terminal states. |
| `raphael/providers/` | Ollama, Whisper and Kokoro adapters implement the chat, recognition and voice provider interfaces. |
| `raphael/realtime/` | Routing, phrase buffering, settings and performance measurement. |
| `raphael/desktop/` | `Controller` coordinates turns. Audio owns capture and playback, `Orb` paints state, Windows integration handles activation and startup, and recovery supervises the process. |
| `raphael/laptop/` | Dispatches supported actions, resolves paths, prepares proposals and handles human decisions. |

## Request and job contract

| Browser operation | Contract |
| --- | --- |
| Submit text | `POST /api/chat` accepts a model selection and a bounded list of user/assistant messages ending in a user message. A successful submission returns HTTP 202 and a job ID. |
| Transcribe | `POST /api/transcribe` receives mono 16-bit PCM WAV at 16 kHz, from 0.25 to 30 seconds. A successful job exposes text. Silence produces a no-speech result and the client skips chat. |
| Synthesize | `POST /api/speak` accepts up to 2,400 characters plus voice options. Each completed job exposes a WAV through `GET /api/audio/{id}`. |
| Observe or stop | `GET /api/jobs/{id}` returns accumulated text, state and details. `POST /api/cancel/{id}` acknowledges cancellation and preserves an existing terminal state. |

The job lifecycle is `queued → generating → ready | error | cancelled`. The default configuration allows two waiting jobs per engine and 24 retained records overall. Completed records expire after 900 seconds. An unavailable engine returns HTTP 503 and a full queue returns 429. Failures after admission are represented in the job state. A client that polls the same job ID can recover its accumulated text without submitting the action twice.

## Turn execution and interruption

1. The chat service obtains the saved profile or uses the request’s profile override. `ProfileStore` caches bounded profile data and checks SQLite’s data version for changes made through another connection.
2. An explicit model choice takes precedence. Automatic selection can use the saved preference or configured routing rules. Standalone conversational requests can use a shorter prompt. Potential laptop actions retain tool validation.
3. The client consumes accumulated text. The speech buffer emits playable phrases while more text is generated. Clients bound prefetch and play one phrase at a time.
4. Stopping a turn cancels outstanding jobs and suppresses stale audio. Browser speech interruption is optional. In the native companion the supported spoken interruption is “Raphael, stop” when enabled.
5. Native orb states are `hidden`, `activating`, `listening`, `thinking`, `speaking` and `deactivating`. Playback completion can transition directly to listening for a follow-up. The hidden orb suspends its paint timer.

## Approval transaction

`Approvals.create` copies the proposal, assigns an ID and records its expiry. The UI presents the operation, target and preview. A decision reaches `POST /api/laptop/approvals/{id}`. Under a lock, the service checks that the proposal is pending. Rejection closes it. Approval changes its state to executing before the stored operation runs, then records completion or failure. A repeated decision on a closed proposal returns HTTP 409. The default expiry is ten minutes and the store is capped at 24 records.

## Startup and failure handling

A second desktop launch uses the existing instance. The current-user Startup shortcut can launch the supervisor after sign-in. An abnormal companion exit triggers retries after 5, 15 and 45 seconds. Ten stable minutes reset the retry budget. A deliberate exit stops recovery. Audio-device errors, job failures and crash recovery are handled separately so restarting an engine job cannot silently repeat a file action.

**References** · [API contracts](https://github.com/Varshith-eati/RAPHAEL_AI/blob/73930aa36fe525fdf24626fd452b9114459d1e6d/docs/api.md) · [Job manager](https://github.com/Varshith-eati/RAPHAEL_AI/blob/73930aa36fe525fdf24626fd452b9114459d1e6d/raphael/services/jobs.py) · [Approval implementation](https://github.com/Varshith-eati/RAPHAEL_AI/blob/73930aa36fe525fdf24626fd452b9114459d1e6d/raphael/laptop/approvals.py) · [Default configuration](https://github.com/Varshith-eati/RAPHAEL_AI/blob/73930aa36fe525fdf24626fd452b9114459d1e6d/config.toml)
