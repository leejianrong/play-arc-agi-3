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
