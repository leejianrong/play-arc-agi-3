# Annotating a game: workflow, files, and fixing up afterwards

How to play so the data is useful, what gets written, and how to review and correct it. Design
decisions live in ADR-0006 to ADR-0009; this is the practical guide.

## Playing

```sh
make run-annotate        # then tick "annotate" in the picker
```

Per level, the loop (the tool only makes it cheap to follow):

1. **Observe** (hands off). Describe objects, colours, symmetries, what looks controllable, what the goal
   might be. Say or add at least one hypothesis.
2. **Probe.** Say a prediction, act, say what happened. Cheap, reversible probes first; one thing at a time.
3. **Plan.** State the rule you've concluded and your confidence, then the plan, before executing.
4. **Execute.** Narrate only surprises. A surprise sends you back to observe/probe.
5. **Reflect** (after a level; `5`). The rule, what misled you, what would be faster.

Keys: `1`-`5` phase · `H` jump to the hypothesis box · `V` dictate hypotheses · `Y`/`N` mark the one marked
"testing" true/false · `T` note · `M` mute. **End session** closes cleanly (and saves the last sentence).

Hypotheses are a list: add several (type + Enter, or dictate), test them, and mark each **true / false**
with its buttons whenever you know, in any order. You can change your mind (reset / re-mark).

Habits that matter more than the keys: keep dead ends in; say predictions *before* acting; say decisions,
not play-by-play; use the same words for the same things; play unfamiliar games; don't read instructions
aloud (you can drop those lines later, see below). Which games to annotate is governed by
`data_policy.json` and ADR-0009 (held-out games are never annotated; public games are `reference-only`).

## What gets written (`recordings/`, gitignored)

Three files per annotated session, same stem `local.<game>.<mode>.<time>`:

| File | Contents |
|------|----------|
| `.recording.jsonl` | one line per step: action, state, levels_completed, available actions, **`frame_sha256`** (the grid itself only in `full` mode) |
| `.annotations.jsonl` | `session_start`, `speech`, `text` (typed), `phase_change`, `hypothesis`, `hypothesis_verdict`, `dictate`, `mute` events, aligned to steps by `step_at_start` / `step_at_end` |
| `.audio.webm` | your raw voice, for re-transcription with a better model later |

## Reviewing

```sh
make timeline                               # the latest annotated session, as markdown on stdout
make timeline FILE=recordings/<x>.recording.jsonl ARGS="--out /tmp/session.md"
make timeline ARGS="--verify"               # also replay the moves and compare every step
```

The timeline groups by level, collapses runs of moves (`steps 2-6: ↑ ↑ ↑ ↑ ←`), puts each thought *after*
the step it reacted to, shows phase changes, and starts with a hypotheses table (verdict, step stated, step
decided). A level number that goes back (after a reset or game over) opens a new "(after reset)" section.

`--verify` replays the recorded actions against the same game locally (no network) and checks every step:
state, levels, and the frame hash. Exit code 0 = identical, 1 = it differs (the message names the first
step and what changed), 2 = could not run. Recordings made before schema 3 have no hashes, so they are
compared on state and levels only (it says so). This is what lets lean recordings stand in for full ones.

## Fixing up (by hand-editing the annotations file)

The CLI never rewrites your data. Open `*.annotations.jsonl` (one JSON object per line) and:

- **Wrong word?** edit `"text"` in that line (re-transcribe from the `.audio.webm` if it's bad).
- **Not part of your thinking** (reading instructions aloud, talking to someone)? add `"ignore": true` to
  that line. The timeline hides it and says how many were hidden; later tooling should skip it too.
- **Mislabelled phase?** edit `"phase"` (or `"phase_at_end"`).

Keep each line valid JSON: an unreadable line is skipped (and reported), never fatal.

## Known limits

- Speech arrives 2-3 s after you stop talking; a sentence is split by a pause longer than 1 s.
- `level` in events is the game's `levels_completed`, which resets to 0 after a game over.
- Training use: only `train-ok` sessions (custom games) are meant for fine-tuning data; there is no exporter yet.
