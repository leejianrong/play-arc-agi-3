# ADR-0011: Agents drive games through a standalone MCP server

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

## Decision

**MCP is the primary interface; Playwright stays the UI test harness.**

- `backend/mcp_server.py`, a stdio MCP server (`python -m backend.mcp_server`) built on the `mcp` SDK, registered
  in `.mcp.json` as `arc-play`. `mcp` is an optional extra (`uv sync --extra agent`), like speech-to-text, so
  running the app does not need it; it is also in the `dev` group so CI runs the protocol tests. `make mcp` runs it by hand.
- **Standalone session.** The server owns one game session, played through `ArcadeGameSource` (ADR-0004) and
  recorded with the same `Recorder` and annotation sidecar as human play. It does not share a session with the
  web app. Starting a new game ends the previous one. Tool calls are sequential, so there is one writer.
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
| MCP bridge into the running web app (shared session, live view, co-play) | The nicest experience, but two writers on one session need a concurrency design (who wins a move, whose recording) before there is any evidence agent play is useful. Deferred; reviewing a session afterwards with `make timeline` covers most of the value. |
| Our own agent loop calling the Claude API | A different project (an evaluation harness); Claude Code as the player is the stated goal. Reconsider for unattended batch evaluation. |
| One PNG per step only | Larger, slower, and the text grid already carries everything. Image stays available for shape judgement. |

## Consequences

- **The restart constraint is real.** Building and testing happens with a Python MCP client in the test suite; to
  actually play, the user restarts Claude Code once so `.mcp.json` is read. Slice V10 starts there.
- **Spoilers.** An agent in this repo can read `custom_games/*.py`, which would make a blind-play evaluation
  meaningless. Blind play therefore runs as a subagent told not to read game sources and results note that it is
  a convention, not a sandbox.
- **Token cost per step is the main unknown.** Native-resolution text keeps custom games small; 64x64 real games
  are several thousand characters per observation. Slice V8 measures this before anything else is built on it.
- The tool surface becomes a contract: renaming a tool or an argument breaks any saved agent prompt.
