# Performance report — 29 October 2026

Measured on this laptop using local Llama 3.2, Kokoro and Whisper base. Values are seconds. Each table cell is **mean / median / P95 / maximum**. P95 is an interpolated description of a very small sample, not a service guarantee.

The benchmark observes the first text available in the backend job, using a 10 ms poll. It does not measure a physical screen update. The browser polls every 160 ms and adds rendering time. Table labels refer to user-visible response content rather than hidden model reasoning.

## Warm response results

The first simple request in each fresh backend run is excluded from this table and shown separately. Simple has two warm trials; normal and reasoning have three trials each.

| Workload and metric | Before | After |
| --- | --- | --- |
| Simple — first visible text | 2.573 / 2.573 / 2.644 / 2.651 | 0.110 / 0.110 / 0.114 / 0.115 |
| Simple — first WAV available | 2.583 / 2.583 / 2.654 / 2.662 | 1.281 / 1.281 / 1.909 / 1.979 |
| Simple — complete model answer | 2.573 / 2.573 / 2.644 / 2.652 | 0.580 / 0.580 / 0.586 / 0.587 |
| Normal — first visible text | 7.955 / 7.918 / 8.224 / 8.258 | 0.262 / 0.147 / 0.477 / 0.513 |
| Normal — first WAV available | 10.527 / 7.928 / 15.149 / 15.951 | 5.166 / 5.138 / 5.361 / 5.386 |
| Normal — complete model answer | 7.955 / 7.918 / 8.224 / 8.258 | 3.980 / 4.295 / 4.703 / 4.749 |
| Reasoning — first visible text | unavailable | 0.287 / 0.115 / 0.588 / 0.641 |
| Reasoning — first WAV available | unavailable | 4.328 / 5.345 / 6.492 / 6.620 |
| Reasoning — complete model answer | unavailable | 5.336 / 5.241 / 5.504 / 5.533 |

## Interpretation

- Warm first text met the 0.5–1.5 second target on these short standalone workloads. The same selected model is used; the fast path removes the laptop action protocol only for conservative standalone conversation. Action requests retain the full original tool definitions and approval checks.
- Normal first-audio median improved from about 7.93 to 5.14 seconds. This remains above the voice target. CPU speech synthesis is now the main remaining delay for fresh longer answers. Text generation and phrase synthesis overlap, but a slow first synthesis can still finish after the text answer.
- Audio means **WAV availability**, not measured speaker onset. Browser/desktop runtime diagnostics separately timestamp playback start. The benchmark does not include physical microphone capture, endpoint waiting, recognition or audio-device latency.
- Voice cache behavior differs: baseline simple trials 2–3 and normal trials 2–3 were cache hits. Optimized warm simple trial 3 was a full cache hit; other optimized normal/reasoning trials were not fully cached. The optimized flag records whether ALL phrases were cached; individual first-phrase cache status was not recorded. Do not present these as identical uncached voice workloads.
- Baseline reasoning returned empty replies in all three trials (roughly 9.7–11.1 seconds), so there is no valid baseline latency comparison for that category. The optimized conversational path completed all three. This is a functional observation, not a reasoning-quality benchmark.
- The first request after launching the baseline took 41.52 seconds to text and 43.77 seconds to audio; optimized took 9.79 and 12.45 seconds. These include model loading and differ in prompt size. OS/model file caches were uncontrolled, so they are not a clean cold-start speedup claim.
- Equivalent questions, local model files, 4,096-token context, configured 360 reply-token budget, thread configuration and saved-profile content were used. Replies are generated, not fixed: answer lengths vary. The original action protocol uses deterministic temperature 0, while the normal conversational adapter retains its configured 0.65. No quality equivalence claim is made.

## What changed and what was already optimized

1. Plain conversational output streams immediately; structured tool replies expose only the reply string after action=reply is known. Full action validation still happens before execution. No invocation JSON is executed from displayed prose.
2. Sentence/word buffering creates a first phrase of roughly 72 characters and later phrases up to roughly 220. At most two prefetched speech jobs are held by each client, with bounded total text/audio and one playback stream. Short complete sentences can start earlier. Partial/final ordering and cancellation are tested.
3. The original three background engine workers are reused. Native/UI work does not perform model inference. Speech preparation can run during model generation. The native companion loads models only when needed.
4. Saved-memory reads reuse a SQLite connection and cached immutable profile; PRAGMA data_version detects other connections changing it. Saves/deletions invalidate the cache. Recent conversational context remains bounded. This was not a major measured baseline bottleneck; no embedding infrastructure was added.
5. Whisper already used CPU INT8, greedy beam size 1, local VAD and no downloads. Those settings are preserved. Recognition now publishes complete segments as available; clients poll every 80 ms. Default call endpoint waiting falls from 1.2 to 0.9 seconds and is configurable. No claim is made that the underlying Whisper model became faster.
6. A real generated 4.5-second recording was recognized in 1.39 seconds in the 0.6 integration test. Physical microphone latency and recognition accuracy in noise remain unmeasured.
7. Optional routing uses local rules rather than another model call. Explicit choices win; missing advanced models fail clearly. It is off by default, because switching loaded models may increase latency.

## Reproduction

Raw evidence: `latency-baseline.json` and `latency-optimized.json`. `latency-streaming-only.json` is an intermediate experiment, not the final configuration. `benchmark_realtime.py` under tests contains the benchmark harness and points to a neighboring preserved baseline source folder by default. Adapt its root paths when running a released package elsewhere. Run without concurrent inference and separate cold/warm/cache-hit results. Physical audio onset needs loopback capture or external measurement.

Diagnostics retain at most 500 samples per stage and optional 512 KB rotating logs (two backups). Only stage names, numbers, clock values and client kind are written. API reports include memory, queue wait, prompt, model-first-token, model-total, TTS startup, transcription, VAD endpoint, tool, first text/audio and completion timings. Model-first-token means first visible text fragment, not hidden reasoning tokens. Runtime logs are not shipped.
