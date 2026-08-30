# ARC Play (play-arc-agi-3): Plan

Status: agreed · Milestone: MVP

## Problem

The official ARC-AGI-3 web UI is laggy and unresponsive, which gets in the
way of actually playing the games. The real games' logic runs exclusively on
ARC's servers — there is no offline reimplementation available — so the fix
has to be a fast local *client*, not a fully offline game.

There's also no way today to record a play session as you go: what you saw,
what you did, and when. That matters because the longer-term goal is an
annotation tool for capturing a human's thought process while solving these
puzzles, and that tool needs something to load.

## Solution

A local web app you start with one command. It opens in your browser, lists
the real ARC-AGI-3 games (and, once slice V2 lands, any custom puzzles you've
authored yourself), and lets you play one with keyboard and mouse against a
fast Canvas-rendered grid. Every action you take and every frame you see is
recorded automatically to a plain file on disk — nothing to remember to save.

## Users and actors

Single primary user: you, playing solo, locally. No multi-user story, no
accounts beyond your own ARC API key. No non-human actors in this milestone
(no agent play, no CI). Nothing to arbitrate — there's only one actor.

## Scope

**In this milestone.**
- Play any real ARC-AGI-3 game through a local, low-latency client
  (R0-R5, R7).
- Automatic, complete recording of every session to a local file (R3, R8).
- Play locally-authored custom puzzle environments through the same UI,
  sequenced after the above (R6).

**Out.**
- Annotation UI — attaching notes/thought-process to frames. This is the
  explicit "eventually," not now; the recording format (ADR-0003) is chosen
  so it doesn't need to change shape when that milestone starts.
- Reviewing/playing back a past recording inside the app. The recordings
  exist and are inspectable as files; a viewer is part of the annotation
  milestone, not this one.
- Agent play, scorecards, or anything competition-submission-related — this
  is a human-play tool.
- Multi-user, cloud sync, mobile. Single laptop, single user.
- Packaging as an installable desktop app (see ADR-0001) — you run a local
  command, not double-click an icon, for now.
- Eliminating network latency to the real games. Their state is authoritative
  on ARC's servers; this project can only remove client-side overhead, not
  the network round-trip. See ADR-0001's Consequences.

## Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| R0 | Play any real ARC-AGI-3 game from a local, responsive UI, authenticated with your own API key | Core goal |
| R1 | The on-screen grid updates on every response with no perceptible client-side rendering delay | Must-have |
| R2 | Support every action type: ACTION1-5 (keyboard), ACTION6 (mouse click with x,y), ACTION7 (undo, when offered), and RESET | Must-have |
| R3 | Every action and the frame it produced is recorded automatically, with no explicit save step | Must-have |
| R4 | List available games — the real catalog, plus discovered local custom envs once R6 lands — and let the user pick one | Must-have |
| R5 | Show live game state: score/levels_completed, win_levels, GameState, available actions | Must-have |
| R6 | Support locally-authored custom puzzle environments through the same play+record flow | Must-have |
| R7 | The API key and any secrets never leave the local machine, and never appear in recordings or logs | Must-have |
| R8 | Recordings are self-contained: a future annotation tool can load one without recontacting any API | Nice-to-have |

## Shape

| Part | Mechanism | ADR |
|------|-----------|-----|
| S1 | `GameSource` interface with two implementations — `RemoteGameSource` (httpx against `three.arcprize.org`) and `LocalGameSource` (wraps `arc_agi.Arcade`) — both producing a normalized `FrameData` | ADR-0002 |
| S2 | FastAPI backend, one WebSocket session endpoint: client sends `start`/`action` messages, server replies with `FrameData` after every `GameSource` call | ADR-0001 |
| S3 | Vanilla JS + Canvas single-page frontend: renders `FrameData.frame` as a colored grid, captures keyboard/mouse, sends WS messages | ADR-0001 |
| S4 | `Recorder`: subscribes to every `FrameData` a `GameSource` produces (including from `reset()`), appends one versioned JSONL line per step | ADR-0003 |
| S5 | `.env`-based `ARC_API_KEY` loaded server-side only; server binds `127.0.0.1` only | — |

## Affordances

**UI.**

| Affordance | Place | Wires to |
|------------|-------|----------|
| Game picker (list + click to start) | Landing screen | WS `start {game_id}` → `GameSource.reset()` |
| Canvas grid | Play screen | Renders latest `FrameData.frame` |
| Keyboard: arrows/WASD, space, backspace, R | Play screen | WS `action {id}` → `GameSource.step()` |
| Mouse click on grid | Play screen | WS `action {id: 6, data: {x,y}}`, coordinates scaled to 0-63 |
| Status/state header (score, levels, GameState) | Play screen | Renders latest `FrameData` metadata fields |
| Error banner | Play screen | WS error events (API failures, missing key, local env exceptions) |

**Non-UI.**

| Affordance | Kind | Wires to |
|------------|------|----------|
| `Recorder.append()` | handler, fired on every `FrameData` | Writes one JSONL line under `recordings/` |
| `RemoteGameSource` | HTTP client | `three.arcprize.org/api/cmd/{RESET,ACTION1-7}` |
| `LocalGameSource` | local process wrapper | `arc_agi.Arcade`, `environment_files/` |

## Implementation decisions

Backend modules: `backend/game_sources/{base.py,remote.py,local.py}` (the
`GameSource` protocol and its two implementations, ADR-0002),
`backend/recorder.py` (ADR-0003), `backend/server.py` (FastAPI app + the one
WebSocket route + game-picker REST endpoint). Frontend is a single
`frontend/index.html` + `frontend/app.js`, no build step, no framework —
matches ADR-0001's bias toward minimal toolchain.

`FrameData` is the one normalized shape everything downstream depends on:
`game_id, guid, source, frame, state, levels_completed, win_levels,
action_input, available_actions`. Both `GameSource` implementations must
produce exactly this shape — enforced by a shared contract test (ADR-0002),
not by inheritance tricks.

Only one session is active per running server process (Q7, ASSUMED). A
second browser tab connecting mid-session is a known MVP limitation, not
handled gracefully — surfacing this cleanly (reject vs. take over) is
deferred, since it's cheap to add a lock later without touching the rest of
the design.

Recording filenames: `recordings/{source}.{game_id}.{guid}.{started_at}.recording.jsonl`,
one file per session, matching the pattern the official `ARC-AGI-3-Agents`
repo already uses for its own recordings.

`make run` is the one-command entry point (dev-playbook principle: runnable
in one command). It defaults to port 8000 (`PORT` env var to prefer another)
but auto-falls back to an OS-assigned free port if the preferred one is
taken, rather than refusing to start — a local dev machine routinely has
something else already bound to a common port. `make test` runs the full
fast layer (pytest + the frontend's `node --test` unit tests); nothing in
this project needs real infra, so there's no separate slow layer yet.

## Testing approach

The seams worth testing: the `GameSource` contract (both implementations
must produce identical-shaped `FrameData` from equivalent inputs — this is
what ADR-0002's abstraction is actually betting on), the WebSocket session
loop (message in → correct `GameSource` call → correct message out →
correct recording line), and the Recorder in isolation (given a sequence of
`FrameData`, does the file on disk match). UI behavior (rendering, input
mapping) is covered by a manual end-to-end pass per slice, since this is a
human-play tool and the actual acceptance test is "does it feel responsive
to play" — not something a headless test can assert.

## Assumed defaults

| ID | Assumed | Cost if wrong |
|----|---------|----------------|
| Q6 | Flat JSONL files, no database | Low — migrating to a DB later is a straight import of existing files |
| Q7 | One active session per server process | Low — add a session lock/registry later without touching `GameSource` or `Recorder` |
| Q8 | Thin custom client, not the `ARC-AGI-3-Agents` framework | Medium — would mean pulling in that framework's dependency surface later if we're ever wrong that it's unneeded |
| Q9 | Canvas rendering, not DOM | Low — isolated to the frontend renderer |
| Q10 | Specific keyboard/mouse mapping | Low — a config-level remap, not a redesign |
| Q17 | 16-color palette guessed from ARC-AGI convention, confirmed empirically | Low — visually obvious and fixed in slice V1 the moment a real game is rendered |

## Open risks

- **Network latency to the real API may still feel slow**, regardless of
  client quality — this is the biggest risk to the core motivation ("laggy
  and unresponsive"). Revealed immediately in slice V1's manual playtest; if
  it's the dominant lag source rather than client-side rendering, that's
  worth knowing before investing further.
- **`arc_agi`'s local `Arcade` API surface** for custom environments is
  understood at the source level (`arc_agi/local_wrapper.py`,
  `arc_agi/base.py`) but not yet built against. Revealed when building
  slice V2.
- **Exact 0-15 color palette** wasn't confirmed from an authoritative source
  during planning. Low risk, immediately visible and fixable in slice V1.

Resolved during V1 build-plan research (2026-08-30), by reading
`arcprize/ARC-AGI`'s own client source (`arc_agi/remote_wrapper.py`,
`arc_agi/api.py`) rather than the hosted docs, which proved incomplete: the
remote API requires a scorecard (`POST /api/scorecard/open` → `card_id`,
passed into the first `RESET`) that earlier research had missed entirely —
see ADR-0002's revised Context; the list-games endpoint is confirmed as
`GET /api/games`; and the rate limit is a generous 600 requests/minute,
non-issue for human play speed.
