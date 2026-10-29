# ARC Play (play-arc-agi-3): Slices

Vertical increments. Each ends in something you can demonstrate. Slice 1
confronts the riskiest unknown: whether play against a real game actually
feels responsive, and whether recording it end-to-end actually works.

> **2026-08-30 update (ADR-0004):** V1 originally built `RemoteGameSource`,
> a per-action HTTP client. After shipping, the user reported it was still
> laggy — that client was the actual cause, not the frontend. It's been
> replaced by `ArcadeGameSource`, which runs real games locally via
> `arc_agi`'s own `NORMAL` mode. The build plan below reflects what's
> actually in the repo now, not the original (slower) version.

## V1: Play a real game, recorded

**Delivers:** R0, R1, R2, R3, R4, R5, R7, R8 — **done**

**Build plan**

1. Scaffold the FastAPI backend and a minimal frontend skeleton (empty
   canvas, WebSocket connects, no game logic yet).
2. Implement `ArcadeGameSource` (`backend/game_sources/arcade.py`): wraps
   `arc_agi.Arcade(operation_mode=OperationMode.NORMAL)`, constructed once
   per WebSocket connection. `reset()`/`step()` normalize
   `arcengine.FrameDataRaw` into our own `FrameData`. `Arcade.make(game_id)`
   downloads a real game's source once (`GET
   /api/games/{game_id}-{version}/source`) and every action after that
   executes locally, in-process — confirmed at 0.5ms/action average against
   a real downloaded game, vs. a full HTTP round trip under the original
   `RemoteGameSource`.
3. Wire the WebSocket route: `start {game_id}` → `reset()`, `action {id,
   data?}` → `step()`, every result pushed back as a `FrameData` message.
4. Frontend: render `frame` into the canvas on every WS message; header
   showing `state`, `levels_completed`, `win_levels`.
5. Input handling: arrows/WASD → ACTION1-4, space → ACTION5, click on the
   grid → ACTION6 with x,y scaled to 0-63, backspace → ACTION7 (only when
   `available_actions` includes it), R → RESET.
6. Implement `Recorder`: append one JSONL line per `FrameData` produced,
   including the one from `reset()`.
7. `.env` loading for `ARC_API_KEY`; refuse to start with a clear error if
   it's missing.

**Demo:** Run `make run`, browser opens to the game picker, pick a real game,
play 20+ mixed actions (movement, a click, a reset), watch the grid update
live — instantly, since every action after the first `start` is local. Then
inspect `recordings/*.jsonl`: line count equals actions taken + 1, every
line parses as JSON, and the `frame` field on the last line matches what's
on screen.

**Rests on assumptions:** Q9 (Canvas rendering — if DOM rendering turns out
fine after all, no harm, this was the safer default anyway); Q17 (color
palette — wrong values are immediately visible and cheap to fix in this
slice).

### Test plan

#### End-to-end

- Launch the app, select a real game, take 5+ mixed actions (movement,
  click, reset); the on-screen grid matches the `FrameData` received at
  each step, and the recording file has one correctly-shaped line per step.
  **Verified live** against the real API (2026-08-30): 25 real games
  listed, one downloaded and played, recording produced correctly.
- A missing/invalid `ARC_API_KEY` produces a visible startup error; the
  server does not start silently broken. **Verified.**
- A `GameSourceError` mid-session (simulated) shows an error banner and
  leaves the recording file intact up to that point. **Verified** (integration test).

#### Integration

- WebSocket session against a stub `ArcadeGameSource`: `start` → 3
  `action`s → the recording file has 4 well-formed JSONL lines in
  step_index order.
- A `GameSourceError` from the game source surfaces as a structured error
  the WS layer forwards, not an unhandled exception that kills the
  connection.

#### Unit

- `ArcadeGameSource.reset()`/`.step()` against a real fixture game
  (`tests/fixtures/environment_files/tst1`, `OperationMode.OFFLINE`, no
  network): correct state transitions, `x`/`y` carried through for
  ACTION6, action id 0 delegates to `reset()`, an unknown game id raises
  `GameSourceError`.
- `Recorder.append()` writes one valid JSON line per call, with
  monotonically increasing `step_index` and the correct filename pattern.
- The keyboard/mouse-to-action mapping resolves each key/click to the
  correct action id and optional `data`.
- `resolve_port()` returns the preferred port when free, falls back to an
  OS-assigned one when it's taken.

## V2: Local custom puzzle environments

**Status (2026-10-30): built** (ARC-92). Five authored games in `custom_games/`, synced into the environments dir at
startup, solver-tested and browser-tested. See `docs/CUSTOM-GAMES.md`.

**Delivers:** R6 — **substantially de-risked by ADR-0004**

`ArcadeGameSource` already runs `OperationMode.OFFLINE` the same way it
runs `NORMAL` (same class, same normalization, same tests structure) — this
slice is now mostly about the picker and docs, not new execution machinery.

**Build plan**

1. Extend the game-picker endpoint to include envs discovered by scanning
   `environment_files/*/*/metadata.json` even when no `NORMAL`-mode
   download has happened yet (currently, `Arcade.available_environments`
   only shows local envs already present on disk — confirm this covers
   hand-authored custom games placed there manually, not just downloaded
   real ones).
2. Write a short in-repo note on adding a new custom environment (points at
   ARC's own `add_game` guide rather than duplicating it).
3. Confirm a hand-authored custom game (not downloaded, no network
   involved) plays end-to-end through the existing WebSocket/session/Recorder
   path with zero code changes — if it needs changes, that's a signal
   `ArcadeGameSource` implicitly assumed `NORMAL`-mode-only behavior
   somewhere.

**Demo:** Add one sample custom environment file under `environment_files/`,
launch the app with no `NORMAL`-mode download involved, see it in the
picker, play it, confirm the resulting recording has `source: "local"`.

**Rests on assumptions:** Q2 (custom local envs are worth this milestone's
time — if not, V2 is simply skipped).

### Test plan

#### End-to-end

- Add a sample custom environment, launch the app, select it from the
  picker, play a few steps; the grid renders and the recording captures
  `source: "local"`.

#### Integration

- The game-picker endpoint correctly lists a hand-placed custom env
  alongside any already-downloaded real games.

#### Unit

- The picker correctly reflects `arcade.available_environments` when a
  custom env's `metadata.json` is malformed (skipped, not a crash) —
  `_scan_for_environments` in `arc_agi` already handles this; confirm our
  own picker endpoint doesn't choke on what it returns.

# Annotation milestone (V3-V6)

Added 2026-10-13. V3 confronts the riskiest unknown: whether live speech from
a (probably Windows-side) browser can reach a local Whisper process, come back
fast enough to be useful, and line up with game steps. Decisions: ADR-0006
through ADR-0009.

## V3: Speak while playing, see live text, saved aligned to steps

**Status (2026-10-14): built** (ARC-65 to ARC-70). Verified in headless Chromium with a fake mic
playing real speech against a real game; numbers in `docs/STT-MEASUREMENTS.md`. Real-microphone
use on this machine is still to be tried by hand.

**Delivers:** R9, R12 (partial: sidecar and alignment, no frame hash yet)

**Build plan**

1. Add the optional `stt` dependency group and a `Transcriber` protocol with a
   fake implementation and a `faster-whisper` implementation (`small.en`).
2. Browser: `audio_worklet.js` captures the mic, downsamples to 16 kHz mono
   PCM16, and streams binary frames on `/ws/audio` with a session-relative
   offset; `MediaRecorder` keeps the opus stream for retention.
3. Backend: `/ws/audio` route tied to the active session; VAD cuts utterances;
   interim text every ~1.5 s while an utterance is open, a final on silence.
4. `AnnotationWriter` appends `session_start` (with `data_use: "unclassified"`
   until V4 adds the policy) and `speech` events to the sidecar, with `step_at_start`, `step_at_end` and `audio_offset_ms`; write
   the audio file beside it.
5. Annotate toggle in the picker (default off, promotes Off to Lean). Live
   transcript panel with interim vs final styling, mic meter, error banner when
   the mic or model fails (session continues).
6. Measure and record: time from end of speech to final text, interim lag, and
   junk-segment rate on key-clatter, on CPU and on GPU if available.

**Demo:** Start an annotated session, say "I think the blue square is the
player" before moving, press a few keys, say "prediction held". Live text
appears beside the grid; the sidecar has two `speech` events whose step ranges
match the moves; the audio file plays back.

**Rests on assumptions:** Q31 (annotated sessions at least Lean; audio kept).
If the mic cannot be captured from the browser in this environment, typed notes
(V4) become the primary path and this slice's result is the evidence for
re-choosing the engine.

### Test plan

#### End-to-end

- A real spoken sentence produces a final transcript whose wording matches
  within a human-judged tolerance, and the sidecar event's step range brackets
  the actions taken while speaking.
- Killing the STT process mid-session shows a banner; play, recording and typed
  notes keep working.

#### Integration

- Feeding a recorded PCM fixture through `/ws/audio` with a fake `Transcriber`
  yields the expected interim then final messages and one `speech` event.
- A `speech` event spanning two game steps records `step_at_start` and
  `step_at_end` correctly.
- With annotate on and record Off, the session starts as Lean.

#### Unit

- VAD segmentation on silence, speech and clatter fixtures yields the expected
  utterance boundaries.
- `AnnotationWriter` writes valid, ordered JSONL with `schema_version: 1`.

## V4: Typed notes, phases, and the data-use policy

**Status (2026-10-14): built** (ARC-71 to ARC-74, plus ARC-82 end-session). Verified in headless
Chromium against the real app with a fake mic: note box, phase chips and auto-advance, mute, held-out
refusal, end session. Held-out games stay playable but unannotated.

**Delivers:** R10, R11 (phases), R14

**Build plan**

1. Typed-note box: `T` focuses, Enter sends a `text` event, Esc cancels; global
   hotkeys are ignored while it has focus.
2. Phase state machine: `observe` at each level start (session start, and when
   `levels_completed` increases); first game action in `observe` auto-switches
   to `probe`; keys `1-5` set the others; every change is a `phase_change`
   event and every later event carries the current phase. Phase chip in the UI.
3. `data_policy.json` with the held-out list from ADR-0009; classify each game
   as `train-ok` (not in the public catalog), `reference-only`, or `heldout`;
   write `data_use` into `session_start`; picker disables annotation for
   `heldout` games with an explanation, while plain play still works.
4. `M` mute key and a `mute` event.

**Demo:** Start an annotated session on a held-out game (annotation toggle is
disabled, play works), then on a normal game: type a note, watch the phase chip
go OBSERVE to PROBE on the first move, press `3` for PLAN, and see all of it in
the sidecar with correct phases and `data_use: reference-only`.

**Rests on assumptions:** Q32 (hotkeys), Q33 (held-out list is arbitrary and
may need editing first).

### Test plan

#### End-to-end

- Typing `T`, a note, Enter does not move the player or trigger ACTION5; after
  sending, arrow keys move again.
- Clearing a level returns the phase to `observe` and logs the change.

#### Integration

- A `start` with annotate on a held-out game is rejected with a structured
  error; with annotate off it plays normally.
- Phase and note events appear in the sidecar in the order they happened,
  sharing the recording's clock.

#### Unit

- Phase machine: auto-advance only from `observe`, level-clear reset, manual
  overrides, and no automatic transition out of `probe`.
- `data_policy.json` classification for held-out, public and custom game IDs,
  and a malformed policy file falls back to refusing annotation.
- Keymap handler ignores hotkeys while a text input is focused.

## V5: Hypothesis tags and the reflect step

**Status (2026-10-14): built** (ARC-75 to ARC-77), then reworked into a list UI (ARC-83) after the first real
session, see ADR-0008's revision. Verified by `make e2e` in headless Chromium: typed and spoken
statements, Y/N/click-to-reopen, struck-through refuted chips, and the level-clear reflect prompt.

**Delivers:** R11 (hypotheses)

**Build plan**

1. Hypothesis registry with stable per-session IDs (`h1`, `h2`, ...); `H`
   opens one and the next utterance or note becomes its statement.
2. `Y` and `N` set the selected hypothesis to confirmed or refuted, emitting
   `hypothesis_verdict` with `step_at_end`; the selected hypothesis ID is
   attached to subsequent events.
3. Hypothesis chips panel (status colours, click to select, defaults to the
   latest open one).
4. On level clear, prompt (non-blocking) for the REFLECT phase and show it in
   the chip.

**Demo:** Say "H, the green block opens the door", move, say "it did not", press
`N`; the chip turns refuted, and the sidecar shows the hypothesis, its tagged
speech, and the verdict linked to the step where it died.

**Rests on assumptions:** none new.

### Test plan

#### End-to-end

- Open two hypotheses, confirm one and refute the other; the chips and
  sidecar both show the right final statuses.

#### Integration

- Events emitted while a hypothesis is selected carry its `hypothesis_id`; after
  a verdict, the selection moves to the next open hypothesis or to none.

#### Unit

- Hypothesis registry: stable IDs, one verdict at most per hypothesis unless
  explicitly reopened, no cross-session leakage.

## V6: Timeline CLI and replay verification

**Status (2026-10-14): built** (ARC-78 to ARC-81). `make e2e` records a session through the real UI, renders it,
and replays it with every step matched by frame hash; a tampered move is caught. Guide: `docs/ANNOTATION-WORKFLOW.md`.

**Delivers:** R12 (frame hash), R13

**Build plan**

1. `Recorder` computes `frame_sha256` for every step, including lean mode, and
   moves to `schema_version: 3`; readers keep accepting v1 and v2.
2. `make timeline FILE=<recording>`: merge recording and sidecar into a
   markdown timeline per level (phase, thoughts, hypotheses with verdicts,
   actions, level results).
3. `--verify`: replay the actions against the same game locally and compare
   every `frame_sha256`; report the first divergence.
4. Document the fix-up workflow: edit the annotations file by hand; the CLI
   never rewrites it. Update `AGENTS.md` with the new modules and the
   gitignored `recordings/` audio.

**Demo:** Run the timeline on the V5 demo session: a readable page showing the
thinking, the probes and the verdicts; `--verify` says all N hashes matched. Edit
one transcript word in the sidecar and see it reflected on the next run.

**Rests on assumptions:** ADR-0005's determinism claim. A failed `--verify` on
any real game is evidence it is wrong for that game.

### Test plan

#### End-to-end

- A session recorded on a real fixture game verifies cleanly; changing one
  action in the recording makes `--verify` fail at that step.

#### Integration

- The timeline for a session with speech spanning several steps orders thoughts
  before the steps they led to, using `step_at_end`.
- v1, v2 and v3 recordings all load; a missing sidecar produces a recording-only
  timeline, not an error.

#### Unit

- `frame_sha256` is stable for identical frames and differs for a one-cell
  change.
- Timeline rendering handles truncated final JSONL lines and unknown event kinds.


## V7: Export annotated sessions as fine-tuning data

**Status (2026-10-30): planned.** ARC-E33 on the board. Decision made: ADR-0010 (a training example is a decision
point). Delivers the exporter that `PLAN.md` listed as out of scope until there was data and a format.

**Build plan**

1. Decide the example format (ADR-0010, `docs/examples/training-example.md`). **Done.**
2. Rebuild every step's frame by replay and refuse sessions that differ from their recorded hashes (ARC-86).
3. Render a frame as a compact text observation with a measured token cost (ARC-87).
4. Pair each thought with the action chunk it led to, with phase and a hypothesis-ledger snapshot (ARC-88).
5. `make export`: JSONL, `train-ok` only by default, held-out always refused, public games only behind an explicit
   flag (ARC-89).
6. Manifest with provenance and a split by game (ARC-90).
7. Independent: re-transcribe kept audio (ARC-91); author custom games, the data bottleneck (ARC-92); ledger-format
   export for the solver (ARC-93).

**Demo:** `make export` over a few custom-game sessions writes `dataset.jsonl` and `manifest.json`; the report
shows examples per phase and hypothesis outcomes; running it on a held-out or public session refuses.

**Rests on assumptions:** ADR-0010's unit of an example. If the first fine-tuning pilot (solver ADR-0012) shows
decision points are the wrong grain, the replay, observation and policy pieces are reused unchanged.

### Test plan

#### End-to-end

- Export from a session recorded through the browser produces examples whose actions match the recording and whose
  hashes verify.
- A held-out, public or unverified session is refused with a non-zero exit code.

#### Integration

- A session with hypotheses yields `ledger_ops` and a ledger snapshot that match the sidecar's events.
- The split never puts one game in both sets.

#### Unit

- Grouping: events at one step merge; silent chunks are dropped; trailing thoughts keep `actions: []`.
- Observation rendering is deterministic.
