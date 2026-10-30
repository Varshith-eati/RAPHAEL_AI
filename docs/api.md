# Local API v1

Base URL defaults to `http://127.0.0.1:8768`. Routes remain `/api/...`; `/api/status` reports `api_version: 1`.

## Additions in 0.6

The native companion requires its session token even for `/api/status`; its owner-restricted IPC opens the browser with a fragment token which is immediately removed from the URL and held in session storage. The browser-only launcher retains the original localhost bootstrap described below.

- `GET /api/interaction`: current validated interaction settings.
- `POST /api/interaction`: partial settings update; unknown fields and invalid values are rejected. Native startup/wake changes require the desktop companion. They are not model tools.
- `GET /api/performance`: bounded per-stage numeric statistics.
- `POST /api/performance`: exactly `stage`, `seconds`, `kind`; allowlisted labels and finite bounded numbers only.
- `POST /api/desktop`: exactly `action`, one of the fixed UI/lifecycle actions. No arbitrary commands.
- Chat model `auto` resolves the saved preferred model or optional local routing rules. Explicit installed model names retain precedence.
- Chat jobs now stream both normal text and eligible structured reply text. Transcription jobs publish segments before completion. A chat job may expose `details.progress` for a tool operation.
- Each speech request still returns one WAV. Clients obtain progressive speech by submitting complete phrases while chat runs, with bounded prefetch and one playback stream.

All original approvals, payload limits and role restrictions remain in force.

Version 0.4.0 adds laptop status to `/api/status`, tool details to chat jobs, and protected laptop/approval routes. See [Laptop access API](laptop-access.md#modules-and-api).

All API responses are JSON except audio. POST requests require `Content-Type: application/json` and a JSON object, including `{}` for cancellation/shutdown, except `/api/transcribe`, which accepts raw WAV bytes. Obtain the token from `/api/status`; send it as `X-Raphael-Token` for all other API requests except `/api/health`. Only loopback Host values and same-origin browser requests are accepted. There is no CORS access from another site.

| Method and path | Result |
| --- | --- |
| `GET /api/status` | App/version, fresh token, chat/voice/transcription states, local model IDs, voices and errors |
| `GET /api/health` | `200` when chat is ready; `503` otherwise. Includes independent engine states |
| `POST /api/chat` | `202 {"id":"..."}` for a queued text reply |
| `POST /api/speak` | `202 {"id":"..."}` for queued speech |
| `POST /api/transcribe` | `202 {"id":"..."}` for queued local microphone recognition |
| `GET /api/jobs/{id}` | State, accumulated text, details, error/code; audio URL when ready |
| `GET /api/audio/{id}` | Generated `audio/wav` after speech completion |
| `POST /api/cancel/{id}` | Idempotent cancellation acknowledgement; completed terminal jobs stay terminal |
| `GET /api/profile` | Saved `name` and `notes` |
| `POST /api/profile` | Atomically validate and replace name/notes, returning the saved profile |
| `POST /api/shutdown` | Acknowledge then stop the application and its owned model service |

Example chat body:

```json
{
  "model": "qwen3.5:4b",
  "messages": [
    {"role": "user", "content": "Help me plan a study session."}
  ]
}
```

Only `user` and `assistant` roles are accepted. Send 1–25 messages, each 1–6,000 characters, at most 18,000 characters total, ending in a user message. An optional `profile: {"name":"...", "notes":["..."]}` overrides memory only for this request; it does not save anything. Omit it to use the database profile. Model context may have a lower token limit than the character budget; shorten older context if needed.

The supplied interface applies a stricter 8,000-character history budget and drops the oldest complete turns first. It shows a notice when this happens; visible messages and explicitly saved memory are retained. API clients remain responsible for budgeting their own conversation context.

Example speech body:

```json
{"text":"Hello. How can I help?", "voice":"heart", "speed":1.0}
```

Text is limited to 2,400 characters. Voices are `heart`, `bella`, `sarah`; speed is 0.8–1.2. Code blocks are replaced with a short spoken note and basic Markdown is removed. Chunking limits native inference windows; the result is one WAV, not streaming audio.

Transcription requires `Content-Type: audio/wav`, the same token and browser boundary checks, and a raw mono 16-bit PCM WAV at 16,000 Hz. Audio must be 0.25–30 seconds, with an overall request limit of 964,096 bytes. Optional `X-Raphael-Language` is `en`, `hi` or `auto`; omission uses the configured language. A successful `kind: transcription` job has recognized text in `text` and timing/language in `details`. It does not automatically submit a chat job: the browser does so after recognition, then requests speech according to the selected mode. Silence yields a `no_speech` job error and no AI request. Recordings are held in memory only.

Job states: `queued → generating → ready | error | cancelled`. `text` grows while chat runs. Example completed result:

```json
{
  "id":"...",
  "kind":"chat",
  "state":"ready",
  "text":"Let's start with your most difficult topic.",
  "error":null,
  "code":null,
  "details":{"model":"qwen3.5:4b","first_token_seconds":1.2,"total_seconds":2.0,"truncated":false}
}
```

HTTP errors have `{"error":"Human-readable message", "code":"stable_code"}`. Typical statuses are 400 for invalid input, 403 for browser/token checks, 404 for expired jobs, 413 for oversized bodies, 415 for wrong content type, 429 for full queues, and 503 for an unavailable engine. Provider failures after admission appear on the job as `state: error`; the polling request itself remains HTTP 200. Do not automatically retry a failed chat without user intent, as it may duplicate work.

The profile allows a name up to 60 characters and 12 nonempty notes up to 500 characters each. Save `{"name":"","notes":[]}` to clear explicit memory. No endpoint stores full conversations, accepts general file uploads or executes model-selected tools.
