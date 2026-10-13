# ADR-0006: Speech is transcribed locally with faster-whisper, captured continuously

- Status: Accepted
- Date: 2026-10-13
- Deciders: Jian (user), agent (recommendation)

## Context

The annotation milestone wants the player's think-aloud as text, aligned to
game steps, good enough to fine-tune a small model on later. Two things drive
the choice: transcript quality on domain words ("sprite", "level", "the 3x3
red block"), and the project's local-only stance (PLAN §Users, R7) -- audio of
the owner's voice should not leave the machine by default.

The backend runs in WSL2 and the browser very likely runs on the Windows host.
That is fine for capture: `getUserMedia` runs in the browser, and `localhost`
is a secure context. The audio just has to cross the existing local WebSocket
boundary.

## Decision

- **Engine:** `faster-whisper` on the backend, default model `small.en`
  (`STT_MODEL` env var to change it; CUDA if available, else CPU int8).
  Everything behind a small `Transcriber` protocol so the engine is swappable.
- **Transport:** the browser captures mic audio, downsamples to 16 kHz mono
  PCM16 in an AudioWorklet, and streams it as binary frames on a dedicated
  `/ws/audio` endpoint (not interleaved with game messages). Speech is aligned to
  game steps by the server: it marks stream time zero on the client's
  `audio_start` message and converts sample counts to session time (more robust
  than client-stamped offsets). The client waits for the server's `ready` status
  before capturing, so audio is never buffered behind a slow model load.
- **Capture mode:** continuous, with voice-activity detection to cut
  utterances, plus a mute hotkey. No push-to-talk. The segmenter is energy-based
  (pure Python, adaptive noise floor from a rolling low percentile, 1000 ms
  closing silence by default via `STT_SILENCE_MS`); Whisper's own VAD filter
  cleans each segment. Measured numbers: `docs/STT-MEASUREMENTS.md`.
- **Interim vs final:** while an utterance is open, the backend re-transcribes
  its buffer about every 1.5 s and sends interim text to the UI. Only the final
  segment (on VAD silence) is stored.
- **Audio retention:** the browser also records the raw stream with
  `MediaRecorder` (opus/webm) and the backend writes it beside the session
  files, so a better model can re-transcribe later. `KEEP_AUDIO=0` disables it.
  Audio is gitignored.
- **Typed notes are always available** (ADR-0007) and need none of this; if the
  mic or model is unavailable the session still works, with a banner.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Browser Web Speech API | Zero install and instant words, but Chrome-only, sends audio to Google, and is weak on domain vocabulary. Worst fit for a dataset whose quality is the point. |
| Hold-to-talk | Cleaner audio, but breaks the flow of thinking and drops the half-formed thoughts that show real reasoning. |
| whisper.cpp subprocess | Fewer Python deps, but a binary to build and manage, and no advantage here since the Python env already exists. |
| Cloud STT (OpenAI, Deepgram) | Better accuracy, but breaks local-only and adds a secret. Could be added behind `Transcriber` later. |

## Consequences

- Adds a heavy dependency (`faster-whisper`, plus a model download of a few
  hundred MB on first use) as an optional extra, so `make check` and CI do not
  need it; tests use a fake `Transcriber`.
- Live text lags speech by roughly 1-3 s, and interim text can change before it
  finalizes. The stored data is only finals.
- Continuous capture will transcribe some noise and keyboard clatter; VAD
  thresholds need tuning in the first slice, and the review step (ADR-0007's
  timeline CLI) is where mistakes get fixed.
- Raw audio makes sessions larger (about 30 MB per hour) and is sensitive; it
  stays local and gitignored.
