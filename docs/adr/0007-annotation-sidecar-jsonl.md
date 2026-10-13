# ADR-0007: Annotations go in a sidecar JSONL aligned to recorded steps

- Status: Accepted
- Date: 2026-10-13
- Deciders: Jian (user), agent (recommendation)
- Extends: ADR-0003 (recording format), ADR-0005 (lean/full modes)

## Context

ADR-0003 chose the recording format so that annotations could be added later
without a migration. The data has to serve two readers: a human who wants to
review and fix a session, and a future fine-tuning pipeline that wants
"reasoning, then action" examples. The sibling `solve-arc-agi-3` project
(ADR-0006 there) extends this trace schema and has a hypothesis ledger with
stable IDs, predictions, evidence and status; the human data should map onto it.

Frames are deterministic (ADR-0005), so a lean recording can always be replayed
to regenerate them, but nothing today verifies that a replay matches.

## Decision

An annotated session writes three files with the same stem:

```text
recordings/local.<game_id>.<mode>.<started_at>.recording.jsonl      (existing)
recordings/local.<game_id>.<mode>.<started_at>.annotations.jsonl    (new)
recordings/local.<game_id>.<mode>.<started_at>.audio.webm           (new, ADR-0006)
```

**Annotation events** are one JSON line each, append-only, with
`schema_version: 1`:

```json
{"schema_version": 1, "event_id": "e17", "t": "2026-10-13T12:00:03.120Z",
 "step_at_start": 12, "step_at_end": 12, "level": 2, "phase": "probe",
 "kind": "speech", "source": "stt", "text": "prediction: up moves the block one cell",
 "audio_offset_ms": [183200, 186900], "hypothesis_id": null}
```

- `kind`: `session_start` (first line; game id, `data_use` from ADR-0009, STT
  model, record mode), `speech`, `text`, `phase_change`, `hypothesis` (new),
  `hypothesis_verdict` (confirmed or refuted, with `hypothesis_id`), `mute`.
- `source`: `stt` or `typed`.
- Alignment is by **step index and time**. `step_at_start` and `step_at_end`
  are the last recorded step when the utterance began and ended, so "thought
  before acting" and "thought after seeing the result" are distinguishable.
  Time is the server clock, in the same clock as the recording's `timestamp`.
- Sessions are self-describing, one file set per session, per-level
  segmentation is by the `level` field, not separate files.

**Recorder change (small, additive):** every recorded step gains
`frame_sha256`, computed even in lean mode, and `schema_version` goes 2 to 3.
This lets a replay verify that regenerated frames match what the player saw.
Old v1/v2 files stay readable.

**Annotation requires recording.** Starting a session with annotation on while
recording is Off promotes recording to Lean. Full stays available.

**Review tooling (this milestone):** a CLI, `make timeline FILE=...`, that
merges the recording and annotations into a readable markdown timeline (steps,
phases, thoughts, hypotheses with verdicts) and, with `--verify`, replays the
actions locally and checks every `frame_sha256`. Transcript fixes are made by
editing the annotations file; the CLI preserves edits by never rewriting it.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Annotations inline in recording lines | Mixes two cadences (steps vs utterances); an utterance spans several steps or none. Forces a Recorder rewrite and complicates a reader that only wants steps. |
| Annotation per step only | Loses thinking that happens with no game step (the whole OBSERVE phase). |
| SQLite | Same reasoning as ADR-0003: no query or concurrency need; flat files are diffable and editable by hand, which the correction step relies on. |
| Full in-app replay viewer and editor | Large slice for a single user who can fix a markdown/JSONL file. Revisit after real sessions show what review needs. |
| Training-format exporter now | Premature before the data exists; the schema keeps `(thought, action)` derivable (thoughts with `step_at_end` before step N precede action N). |

## Consequences

- A reader that wants a training example joins two files by step index; that is
  a one-screen script, and the CLI already does it.
- Corrupt or truncated sidecars degrade gracefully (JSONL), same as recordings.
- `frame_sha256` makes silent nondeterminism visible; if a game ever fails
  verification, ADR-0005's determinism claim is wrong for that game and lean
  recordings of it are not trustworthy.
- No exporter or in-app viewer yet; reviewing is by markdown file.

## Implementation notes (V6, 2026-10-14)

- `frame_sha256` is the sha256 of the frame's canonical JSON (`separators=(",", ":")`), recorded on every step
  including lean mode; schema 3. Readers accept 1, 2 and 3.
- `make timeline` places each annotation after the step in `step_at_end` and before the next action. A new
  section starts on a level change, a reset, or a level regression (`levels_completed` resets to 0 after a game
  over), so attempts read separately. Events with `"ignore": true` are hidden and counted.
- `--verify` replays in OFFLINE mode from `environment_files/` (or `--env-dir`), so it needs no network or key. It
  compares state, levels and (when recorded, or derivable from a full-mode frame) the frame hash, and reports the
  first divergence. Older recordings are compared on state and levels only. Exit codes: 0 same, 1 differs, 2 error.
- Checked on the first real sessions (ls20, 142 steps including a game over; r11l, 9 steps): both replay
  identically on state and levels, supporting ADR-0005's determinism claim for those games.
