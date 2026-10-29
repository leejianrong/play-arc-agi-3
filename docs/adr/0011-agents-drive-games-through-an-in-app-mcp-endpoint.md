# ADR-0011: Agents drive games through an MCP endpoint inside the app

- Status: Accepted
- Date: 2026-10-30
- Deciders: Jian (user), agent (recommendation)
- Relates to: ADR-0004 (local execution), ADR-0007 (sidecar), ADR-0010 (decision points); `solve-arc-agi-3`

## Context

The goal is for Claude Code to play these games: to test how learnable the custom games are, to produce agent
traces that can be compared with human ones, and to prototype strategies for the solver. Two routes exist.
Driving the web UI with a browser tool (Microsoft's `@playwright/mcp`, Apache-2.0, or our own Playwright
harness) works with no new code but means pixels in and keypresses out: slow, lossy, and hard to test.
A purpose-built MCP server lets the agent call `observe` and `act` directly against the same game code the app
uses. The official Python `mcp` SDK is MIT licensed. Claude Code loads MCP servers from `.mcp.json` at session
start, so a new server can only be used after a restart; tests must therefore not depend on Claude Code.

First draft chose a standalone stdio server to avoid a shared-session design. Revised the same day, before any code,
on the user's point that the app already spins up and runs the games: a second process would duplicate game start,
recording and annotation, and could not show the user anything live. `mcp` 2.3.0 (stable, MIT) is current on PyPI.

## Decision

**MCP is the primary interface; Playwright stays the UI test harness.**

- `backend/mcp_server.py` builds an MCP server on the `mcp` SDK (v2, streamable HTTP) and `backend/server.py` mounts
  it at `/mcp` in the same FastAPI app, so `make run` starts the UI and the agent endpoint together. It is
  registered in `.mcp.json` as `arc-play` with `{"type": "http", "url": "http://127.0.0.1:8000/mcp"}` (host and port
  follow `make run`). `mcp` is a normal dependency (it is small, and the endpoint is part of the app); CI runs the
  protocol tests with a real MCP client over HTTP against the ASGI app.
- **One code path.** The endpoint uses the app's `ArcadeGameSource` (ADR-0004), `Recorder`, `AnnotationSession`
  and data policy through a small session manager that the WebSocket loop and the MCP tools both use. No second
  implementation of start, step, record or annotate.
- **Single writer, agent-owned sessions, human spectator.** A session is owned by one actor, `human` or `agent`.
  A game started through MCP is agent-owned: the browser shows it live as a read-only view (grid, step, state,
  the agent's notes, hypotheses and phase) on a `/ws/watch` socket, and its input is disabled. The agent cannot
  touch a human-owned session and the human cannot move in an agent-owned one, so there is no move conflict
  and nothing to merge. Shared control (the human takes over mid-game) is deferred until there is evidence it
  is wanted. The agent starts at most one session; starting another ends the first.
- **Tools.** `list_games`, `start_game(game_id, max_actions=300, allow_heldout=false)`, `observe(image=false)`,
  `act(action, x?, y?, thought?)`, `reset`, `end_session`, and the thinking tools `note`, `hypothesis_add`,
  `hypothesis_verdict`, `set_phase`. `act` accepts `up/down/left/right/act/click/undo` or `ACTION1..7`, rejects
  actions the game does not offer (the error lists the ones it does), and returns the new observation, so a
  normal loop is one call per move. The thinking tools write the same annotation events a human does (ADR-0007,
  ADR-0008), with `source: "agent"`.
- **Observation is text by default, a PNG on request.** The text view is the frame at its **native resolution**
  (the 64x64 frame is an integer upscale of the game's real grid, so a 16x16 game is sent as 16x16), one character
  per cell (`0-9a-f`), a legend of the colours present, a header (step, state, levels, available actions), and a
  list of cells that changed since the last observation, capped. This is a first version of the encoder that
  ADR-0010 and ARC-87 need; ARC-87 later adds objects. The PNG is a nearest-neighbour upscale with the app's
  palette, returned as MCP image content.
- **Budget.** Each session has a cap on actions (default 300, reset counts); exceeding it returns an error
  and the session stays inspectable. Errors are returned as MCP tool errors, never as crashes; unknown game,
  no active session, and an action the game does not offer each have a specific message.
- **Real games** are available when `ARC_API_KEY` is set and games are downloaded, exactly like the app.
- Session files live in `recordings/` with the stem prefix `agent.` so they sort apart from human sessions, and
  work with `make timeline` and `--verify` unchanged.

## Alternatives considered

| Option | Why not (first) |
|--------|-----------------|
| Drive the browser with Playwright / `@playwright/mcp` as the main route | Works today and remains the way to check the UI, but every observation is a screenshot to interpret and every move a key press; slow, costly in tokens, impossible to unit test, and says nothing the game state does not. |
| Standalone stdio server (the first draft) | Duplicates what the app does, cannot show the user a live game, and cannot reuse the running app's state. Its only advantage was no dependency on `make run`. |
| Shared session with two writers (human and agent move the same game) | Needs a concurrency design (who wins a move, whose recording) before there is evidence agent play is useful. Agent-owned sessions with a spectator view give most of the value. Deferred. |
| Our own agent loop calling the Claude API | A different project (an evaluation harness); Claude Code as the player is the stated goal. Reconsider for unattended batch evaluation. |
| One PNG per step only | Larger, slower, and the text grid already carries everything. Image stays available for shape judgement. |

## Consequences

- **The restart constraint is real.** Building and testing happens with a Python MCP client in the test suite; to
  actually play, the user restarts Claude Code once so `.mcp.json` is read, with `make run` already up. If the app
  is not running the `arc-play` tools show as failed to connect, which is the expected state, not a bug.
- **Local-only exposure.** The endpoint binds like the rest of the app (127.0.0.1) and has no authentication,
  which is acceptable for a single-user local tool; the `Origin` header is checked so a web page cannot drive it
  (the SDK's DNS-rebinding protection is left on).
- **Spoilers.** An agent in this repo can read `custom_games/*.py`, which would make a blind-play evaluation
  meaningless. Blind play therefore runs as a subagent told not to read game sources and results note that it is
  a convention, not a sandbox.
- **Token cost per step is the main unknown.** Native-resolution text keeps custom games small; 64x64 real games
  are several thousand characters per observation. Slice V8 measures this before anything else is built on it.
- The tool surface becomes a contract: renaming a tool or an argument breaks any saved agent prompt.
