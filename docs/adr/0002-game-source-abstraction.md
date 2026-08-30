# ADR-0002: GameSource abstraction over remote API and local `arc_agi` envs

- Status: Partially superseded by [ADR-0004](0004-local-execution-via-arc-agi-toolkit.md)
- Date: 2026-08-30
- Deciders: Jian (user), agent (recommendation)

> **2026-08-30 update:** the "real games can't run locally" premise below
> was wrong — see ADR-0004. `RemoteGameSource` and the remote/local split
> described here were replaced by a single `ArcadeGameSource`. This ADR is
> kept for the historical record and because the underlying research on the
> REST API contract (scorecard lifecycle, FrameData shape) is still
> accurate and still used by `arc_agi` itself.

## Context

Two distinct game corpora exist for ARC-AGI-3:

1. The real competition games (`ls20`, `ft09`, …), served exclusively via
   `three.arcprize.org`'s REST API. Their rule logic is not open source, so
   there is no way to run them offline — "local" can only mean a local
   *client*.
2. Custom puzzle environments, which a user can hand-author as Python game
   code (`ARCBaseGame`, `Sprite`, `Level` classes) and run fully locally via
   ARC's `arc_agi.Arcade` toolkit. This is a different workflow — writing a
   puzzle, not solving one — from a different corpus.

The user wants both in scope. Confirmed via `docs.arcprize.org/api-reference`
and `docs.arcprize.org/add_game`, and by inspecting `arcprize/ARC-AGI-3-Agents`
(commit as of 2026-08-30):

- Remote API: session lifecycle is scorecard → reset → actions → close.
  `POST https://three.arcprize.org/api/scorecard/open` (header `X-API-Key`,
  body `{tags: ["human"], ...}`) returns `{card_id}`. `POST
  /api/cmd/RESET` with `{card_id, game_id}` starts a session and returns a
  `guid`; every subsequent `POST /api/cmd/{RESET|ACTION1-7}` sends
  `{game_id, guid, x?, y?, reasoning?}` — `x`/`y` (ACTION6 only, each 0-63)
  go directly on the payload, not nested under a `data` object. Every call
  returns `{game_id, guid, frame: int[][][], state:
  NOT_PLAYED|NOT_FINISHED|WIN|GAME_OVER, levels_completed, win_levels,
  action_input, full_reset?, available_actions}`. `frame` cells are 0-15
  (4-bit color index) over one or more 64×64 grids. `POST
  /api/scorecard/close {card_id}` ends the session. Confirmed by reading
  `arcprize/ARC-AGI`'s own `arc_agi/remote_wrapper.py` and `arc_agi/api.py`
  source directly (commit as of 2026-08-30) after the hosted API docs proved
  incomplete/inconsistent on this point.
- Local: `arc_agi.Arcade(environments_dir=...).make(game_id, seed=..., render_mode=...)`,
  then `env.step(GameAction, data=...)`. Game files live under
  `environment_files/{game_id}/v1/{game_id}.py` + `metadata.json`.

The official `arcprize/ARC-AGI-3-Agents` repo wraps both behind an
agent-competition framework (LangGraph templates, AgentOps tracing, swarm
orchestration, scorecards) that this project does not need.

## Decision

Define one `GameSource` interface — `list_games()`, `reset(game_id)`,
`step(action_id, data=None)` — each returning a normalized `FrameData` value
(the fields above, plus a `source: "remote" | "local"` tag). Implement it
twice:

- `RemoteGameSource`: a thin `httpx.Client` (one persistent client per
  session, so cookies set by the API's load balancer carry across calls —
  the official client does this too) against the REST API above. It owns
  the scorecard lifecycle internally: opens one scorecard on construction,
  passes its `card_id` into the first `RESET`, and closes it when the
  session ends — callers of `GameSource` never see `card_id`.
- `LocalGameSource`: a thin wrapper around `arc_agi.Arcade`, scanning
  `environment_files/*/*/metadata.json` for `list_games()`.

The rest of the app (WebSocket session handling, rendering, recording — see
ADR-0003) depends only on `GameSource` and `FrameData`, never on which
implementation is active. Slice V1 ships `RemoteGameSource` only; slice V2
adds `LocalGameSource` behind the same contract — see `SLICES.md`.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Remote-only, drop local custom envs | Simplest, but drops an explicit requirement (R6) the user confirmed they want, just deferred to slice V2 rather than dropped. |
| Depend on `ARC-AGI-3-Agents` directly for both sources | That framework's surface (LangGraph, AgentOps, swarm) is built for autonomous-agent competition entries, not a human-play recorder, and couples this project to that repo's release cadence and dependency footprint for no benefit. |
| One combined "UniversalGameSource" class with an internal mode flag | Rejected in favor of two classes behind one interface — a mode flag inside one class tends to grow branching as the two sources' failure modes diverge (network errors vs. local Python exceptions), while two classes keep those concerns separate from the start. |

## Consequences

- A shared contract test (same test suite run against both implementations)
  becomes the thing that keeps the normalization honest — worth writing
  before slice V2, not after.
- Local custom environments require the user to hand-write Python game code
  per ARC's `add_game` guide; this is a real authoring workflow, not a
  toggle, and is explicitly sequenced after the core play+record loop ships.
- If ARC's remote API or `arc_agi` package changes shape, only one
  implementation needs updating, not the whole app.
