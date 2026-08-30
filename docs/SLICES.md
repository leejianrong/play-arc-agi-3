# ARC Play (play-arc-agi-3): Slices

Vertical increments. Each ends in something you can demonstrate. Slice 1
confronts the riskiest unknown: whether a lean local client actually feels
responsive against the real remote API, and whether recording it end-to-end
actually works.

## V1: Play a real game, recorded

**Delivers:** R0, R1, R2, R3, R4 (remote only), R5, R7, R8

**Build plan**

1. Scaffold the FastAPI backend and a minimal frontend skeleton (empty
   canvas, WebSocket connects, no game logic yet).
2. Implement `RemoteGameSource`: on construction, open a scorecard (`POST
   /api/scorecard/open`) and hold its `card_id`; `reset(game_id)` sends
   `POST /api/cmd/RESET {card_id, game_id}`; `step(action_id, data)` sends
   `POST /api/cmd/{ACTION1-7} {game_id, guid, x?, y?}` (`x`/`y` top-level,
   ACTION6 only); a shutdown hook sends `POST /api/scorecard/close
   {card_id}`. Plus `GET /api/games` for the picker. All with the
   `X-API-Key` header, one persistent `httpx.Client` per session so
   load-balancer cookies carry across calls.
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

**Demo:** Run the app, browser opens to the game picker, pick a real game
(e.g. `ls20`), play 20+ mixed actions (movement, a click, a reset), watch
the grid update live. Then inspect `recordings/*.jsonl`: line count equals
actions taken + 1, every line parses as JSON, and the `frame` field on the
last line matches what's on screen.

**Rests on assumptions:** Q9 (Canvas rendering — if DOM rendering turns out
fine after all, no harm, this was the safer default anyway); Q17 (color
palette — wrong values are immediately visible and cheap to fix in this
slice).

### Test plan

#### End-to-end

- Launch the app, select a real game, take 5+ mixed actions (movement,
  click, reset); the on-screen grid matches the `FrameData` received at
  each step, and the recording file has one correctly-shaped line per step.
- A missing/invalid `ARC_API_KEY` produces a visible startup error; the
  server does not start silently broken.
- An API error mid-session (simulate with a bad `game_id`) shows an error
  banner and leaves the recording file intact up to that point.

#### Integration

- WebSocket session against a mocked `RemoteGameSource`: `start` → 3
  `action`s → the recording file has 4 well-formed JSONL lines in
  step_index order.
- `RemoteGameSource` surfaces a 401/400 from the API as a structured error
  the WS layer forwards, not an unhandled exception that kills the
  connection.

#### Unit

- `RemoteGameSource.step()` maps a `GameAction` id + optional `(x, y)` to
  the correct HTTP request, and parses a `FrameResponse` fixture into the
  normalized `FrameData`.
- `Recorder.append()` writes one valid JSON line per call, with
  monotonically increasing `step_index` and the correct filename pattern.
- The keyboard/mouse-to-action mapping resolves each key/click to the
  correct action id and optional `data`.

## V2: Local custom puzzle environments

**Delivers:** R6

**Build plan**

1. Implement `LocalGameSource` wrapping `arc_agi.Arcade(environments_dir=...)`,
   normalizing its output into the same `FrameData` shape `RemoteGameSource`
   produces.
2. Extend the game-picker endpoint to also list envs discovered by scanning
   `environment_files/*/*/metadata.json`, tagged `source: "local"`.
3. Confirm the WebSocket/session/`Recorder` code path needs zero changes
   beyond source selection — if it does, that's a signal S1's abstraction
   (ADR-0002) leaked and needs tightening before this slice is done.
4. Write a short in-repo note on adding a new custom environment (points at
   ARC's own `add_game` guide rather than duplicating it).

**Demo:** Add one sample custom environment file, launch the app, see it
appear in the picker tagged "local," play it the same way as a remote game,
confirm the resulting recording has `"source": "local"` on every line.

**Rests on assumptions:** Q2 (custom local envs are worth this milestone's
time — if not, V2 is simply skipped without touching V1); the exact shape of
`arc_agi.Arcade`'s local output (an open risk in `PLAN.md` — confirmed by
building this slice).

### Test plan

#### End-to-end

- Add a sample custom environment, launch the app, select it from the
  picker, play a few steps; the grid renders and the recording captures
  `source: "local"`.

#### Integration

- The game-picker endpoint returns both a mocked remote games list and a
  discovered local env, each correctly tagged by `source`.

#### Unit

- A shared contract test run against both `RemoteGameSource` and
  `LocalGameSource`: given equivalent inputs, both produce `FrameData` with
  identical field shapes and types.
- The `environment_files` scanner correctly parses a valid `metadata.json`
  and skips a malformed one without crashing the game picker.
