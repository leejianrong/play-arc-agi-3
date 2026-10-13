# Speech-to-text measurements (ARC-70, slice V3)

Measured 2026-10-14 on the dev machine: WSL2, 16 cores, 7 GB RAM, **no GPU** (CPU int8),
`faster-whisper` 1.2.1, `beam_size=1`, `temperature=0`. Audio is the 11 s JFK clip from the
Whisper repo (clean speech, so these are best-case accuracy numbers).

## Transcription latency (warm model, per call)

| Model | Load (cached) | Peak RSS | 1.5 s clip | 4 s clip | 11 s clip |
|-------|---------------|----------|------------|----------|-----------|
| `small.en` (default) | 2.3 s (21 s first run, incl. download) | ~0.8-1.5 GB | 1.35 s | 1.35 s | 1.56 s |
| `base.en` | 1.5 s (8 s first run) | ~0.4 GB | 0.46 s | 0.52 s | 0.70 s |

Latency is roughly flat in clip length, so an interim costs about the same early or late in an
utterance. Before `temperature=0.0` was set, `small.en` took 2.7-3.2 s on cut-off 4 s interims
because Whisper re-decoded at higher temperatures; that is now disabled.

## What the user sees (real browser, fake mic playing the clip, real game)

- Page load to "listening": about 1 s once the model is warm; about 20 s on the very first run
  (model download, `small.en` is a few hundred MB).
- Interim text first appears about 1.5-2 s into an utterance and refreshes about every 1.5 s of
  speech. Interims of cut-off audio are rough ("ask for a free speech" for "ask not what your
  country...") and always replaced by the final.
- Final text lands about 1.0 s of silence + 1.4 s of transcription = **roughly 2.5 s after you stop
  talking** (`STT_SILENCE_MS` default 1000).
- Step alignment verified with real keypresses: an utterance spoken over game steps 4-6 is stored
  with `step_at_start=4`, `step_at_end=6`.

## Junk rate

A 30 s loop of room hiss plus about 45 key-press clicks (two decaying bursts each, 9000 peak
amplitude) played into the browser: **0 transcripts, 0 events**, while the meter peaked at 79% (the
audio was captured and judged to be non-speech by the segmenter).

## Decisions from the numbers

- Keep `small.en` as the default: finals are accurate, and 1.4 s per call is acceptable on CPU.
- `STT_MODEL=base.en` is the lever if the lag feels slow (about 3x faster, a bit less accurate).
- A GPU was not available, so the CUDA path is untested.
- The 700 ms silence boundary originally planned split sentences at ordinary commas and hurt
  Whisper's context ("Ask not!"); the default is now 1000 ms. Pauses longer than that still split.

## Known limits

- An unbroken, steady loud signal (no gaps) is treated as background after the noise floor adapts
  (about 1 s warm-up). Real speech always has gaps; synthetic tones in tests need them.
- Only one speaker and English (`*.en` models) are supported.
