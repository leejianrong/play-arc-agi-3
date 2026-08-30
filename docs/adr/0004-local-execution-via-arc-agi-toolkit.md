# ADR-0004: Run real games locally via arc_agi's NORMAL mode, not per-action remote calls

- Status: Accepted
- Date: 2026-08-30
- Deciders: Jian (user), agent (recommendation)
- Supersedes: ADR-0002's remote-execution decision (`RemoteGameSource`).
  ADR-0002's local-custom-environment decision stands, and this ADR
  generalizes it.

## Context

After slice V1 shipped, the user reported it was "still laggy and not very
snappy/responsive," and separately hit a raw `400 Bad Request` from
`ACTION3` mid-session that looked like a move-limit but wasn't (see
Consequences).

`RemoteGameSource` (ADR-0002) called `POST /api/cmd/ACTION{n}` on
`three.arcprize.org` for every single action — a full network round trip per
move. That was the actual cause of the lag; client-side rendering, the thing
ADR-0001 optimized for, was never the bottleneck.

ADR-0002 stated "the real games' logic is not open source... there is no
way to run them offline." That was wrong. Re-reading `arcprize/ARC-AGI`'s
own source (`arc_agi/base.py`) surfaced `OperationMode.NORMAL` — the
package's own default mode, which this project had never used. In `NORMAL`
mode, `Arcade.make(game_id)`:

1. Calls `GET /api/games/{game_id}-{version}/source` **once**, saving the
   real game's Python source to `environment_files/{game_id}/{version}/`.
2. Dynamically loads and executes that source via the same
   `LocalEnvironmentWrapper` mechanism ADR-0002 already planned to use for
   hand-authored custom environments (`OperationMode.OFFLINE`).
3. Every subsequent `reset()`/`step()` call runs **entirely locally,
   in-process** — confirmed by reading `arc_agi/local_wrapper.py`, which
   contains no network calls at all in its step/reset path.

Measured directly against a real downloaded game (`re86`): 10 local
`ACTION1` calls averaged **0.5ms** each, versus a full HTTP round trip to
`three.arcprize.org` under the old `RemoteGameSource`. The one-time
download (metadata + source fetch) took ~2s.

`arc_agi` (PyPI: `arc-agi`) and its dependency `arcengine` are both
MIT-licensed — clean to depend on directly (verified via
`importlib.metadata`).

## Decision

Retire `RemoteGameSource` entirely. Replace it with `ArcadeGameSource`
(`backend/game_sources/arcade.py`), a thin wrapper around `arc_agi.Arcade`
running in `OperationMode.NORMAL`. One `Arcade` instance is constructed per
WebSocket connection (not per game) so switching games mid-session reuses
the same catalog fetch and scorecard.

Both real games (`NORMAL` mode, downloaded once) and hand-authored custom
puzzles (`OFFLINE` mode, slice V2) now execute through the exact same local
path and are tagged `source: "local"` in `FrameData` — there is no more
`"remote"` source. This collapses what ADR-0002 planned as two separate
`GameSource` implementations (`RemoteGameSource` + `LocalGameSource`) into
one (`ArcadeGameSource`), since both were always going to be thin wrappers
around the same underlying `arc_agi.Arcade` type, just constructed with a
different `operation_mode`.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Keep `RemoteGameSource` for real games, add a separate `LocalGameSource` only for custom envs (ADR-0002's original plan) | The user never asked for slower play — now that real games can run locally too, keeping a deliberately-slower path around serves no one. |
| Build our own source-download + dynamic-exec engine instead of depending on `arc_agi` | Would duplicate a non-trivial, already-open-source, already-tested engine (sprites, camera, levels, collision — the `ARCBaseGame` contract in `arcengine`) for no benefit. Same reasoning ADR-0002 already used to reject reimplementing the remote protocol. |
| Cache remote frames client-side to mask per-action latency (optimistic UI) | Doesn't fix the actual problem — the server is still authoritative and every action still needs a real round trip eventually. Local execution removes the round trip altogether. |

## Consequences

- Adds `numpy`, `pillow`, `matplotlib`, and `flask` as transitive
  dependencies (needed by `arcengine`'s rendering/game-engine internals and
  `arc_agi`'s own optional REST server, which this project doesn't use).
  All MIT-licensed; ~30MB extra on disk. Acceptable for a local single-user
  dev tool with no deployment-size constraint.
- **No online scorecard or shareable replay is created.** Confirmed from
  source: `Arcade.close_scorecard()` in `NORMAL` mode routes through a
  local, in-memory `ScorecardManager`, not the real `/api/scorecard/*`
  endpoints — those only activate in `ONLINE`/`COMPETITION` mode. This
  project never asked for leaderboard visibility, so this is a non-issue,
  but it's a real behavior change from what `RemoteGameSource` did.
- **The specific 400 error the user hit is structurally eliminated, not
  just less likely.** It was caused by the remote server's `_get_or_create_environment`
  looking up a cached game instance by `guid`, which gets evicted when
  ARC's server auto-closes an idle scorecard after 15 minutes
  (`STALE_MINUTES` in `arc_agi/scorecard.py`). Local execution never does a
  guid-based cache lookup per action — `ArcadeGameSource` holds a direct
  reference to the in-memory game object — so there is no server-side state
  to go stale between actions.
- First play of a not-yet-downloaded game still pays one network round
  trip (source download, ~2s observed); every action after that is local.
  A game already downloaded in a prior session loads from disk with no
  network call at all.
- `RemoteGameSource` and its tests are deleted rather than kept alongside
  the new path — an unused, deliberately-inferior implementation is dead
  weight, not a hedge.
