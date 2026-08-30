# ADR-0005: Recording is opt-in, off by default, with a lean mode

- Status: Accepted
- Date: 2026-08-31
- Deciders: Jian (user), agent (recommendation)
- Amends: ADR-0003's "automatic, no explicit save step" decision and PLAN.md
  requirement R3.

## Context

Full-mode recordings (ADR-0003) capture the actual frame grid on every
step. For a real game played for a while, that adds up fast — one session
hit 25MB. The user found this out by actually running the app: recording
was automatic and always-on, so every play session, including throwaway
ones, silently accumulated a large file.

Separately, the user asked whether a lighter recording mode — actions
without frames — was viable, reopening a question ADR-0003 had explicitly
rejected. That rejection was based on the old remote-execution
architecture: sessions/guids could expire, and there was no confirmed way
to reproduce a past game's frames from its actions alone. Under ADR-0004's
local execution, that concern no longer applies *if* the games are
deterministic. Checked directly: `arcengine` (the actual game engine) has
exactly one call to a randomness source in its entire source — `uuid.uuid4()`
used as a fallback internal name for an unnamed sprite, which affects no
rendered pixel or game-logic branch.

The `seed` parameter exists on
`ARCBaseGame` but is stored and never read anywhere in the engine; the
downloaded real games (checked `cd82`) don't even declare a `seed`
parameter. **The games are deterministic**: the same game plus the same
action sequence always produces the same frames.

## Decision

Recording defaults to **off**. The picker screen has a `Recording: Off /
Lean / Full` control (default `Off`); the chosen mode travels with the
WebSocket `start` message and is fixed for that session — no mid-session
change.

Two recording modes when it's on:

- **Full**: unchanged from ADR-0003 — every line includes the frame grid.
- **Lean** (new): every line includes everything *except* the frame grid
  (`"frame": null`) — action, state, levels_completed, win_levels,
  available_actions. Because games are deterministic, a lean recording's
  frames are always reconstructable later by replaying its action sequence
  against the same game, entirely locally.

`Recorder` takes a `mode` and writes it into `schema_version: 2`'s
`"mode"` field on every line, and into the filename
(`{source}.{game_id}.{mode}.{started_at}.recording.jsonl`) so a directory
listing alone shows which recordings need a replay to see their frames.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Keep recording automatic, just add a lean mode | Doesn't address the actual complaint — most sessions are throwaway play, not something worth recording at all. Opt-in is the fix; lean mode is a size reduction for when you do want it. |
| Compress full recordings (gzip) instead of a lean mode | Cuts size but keeps paying the cost of writing megabytes of frame data on every step, and a compressed JSONL can't be tailed/greped as easily. Doesn't need a replay tool, but doesn't solve the "recording things I don't want recorded" problem either — orthogonal to opt-in, and left for later if lean mode alone isn't enough. |
| Confirm-dialog per game start ("Record this session?") | Considered and dropped in favor of a persistent dropdown — one interruption-free control beats a dialog on every single game launch for a single-user tool used repeatedly in one sitting. |

## Consequences

- No replay tool exists yet to actually reconstruct frames from a lean
  recording. Building one is now an explicit dependency of the future
  annotation-tool milestone, not optional infrastructure it can skip.
- `schema_version` bumped to 2 (added `mode`). Old (version 1) recordings
  from before this change have no `mode` field and are implicitly `full`
  — a future reader should treat a missing `mode` as `full` for backward
  compatibility, not fail to parse.
- The determinism finding is a property of today's engine and downloaded
  games, not a guarantee ARC makes contractually. If a future game version
  introduces real randomness, lean recordings of it would stop being
  reconstructable — low risk (nothing found today suggests this direction),
  but worth re-checking if `arcengine` or a game's behavior ever looks
  session-dependent in a way a fixed action replay can't reproduce.
