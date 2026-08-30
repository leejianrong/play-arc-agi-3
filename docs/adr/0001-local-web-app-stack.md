# ADR-0001: Local web app — FastAPI + WebSocket backend, Canvas frontend

- Status: Accepted
- Date: 2026-08-30
- Deciders: Jian (user), agent (recommendation)

## Context

The official ARC-AGI-3 web UI feels laggy and unresponsive. The actual game
logic for real competition games runs on ARC's servers — it is not open
source — so a local build cannot eliminate network round-trips to
`three.arcprize.org`. What it *can* eliminate is client-side overhead: however
the official site renders its grid, a 64×64-cell view re-rendered on every
action is exactly the shape of workload that gets slow if done through the DOM.

The project needs: fast iteration to an MVP, cross-platform support (the user
is on a laptop, platform unspecified beyond that), keyboard and mouse input
capture, and a foundation that can grow into an annotation tool later (text
panels, timelines, notes tied to frames) without a rewrite.

## Decision

Build a local web app: a Python **FastAPI** backend exposing a WebSocket
session endpoint, and a single-page **vanilla JS + HTML5 Canvas** frontend,
served on `127.0.0.1` and opened in the user's default browser. The backend
owns all game-source communication (see ADR-0002) and recording (see
ADR-0003); the frontend is a thin renderer plus input capture.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Electron / Tauri desktop wrapper | Adds a packaging and build toolchain for no functional gain at MVP — same web UI, just wrapped. Worth revisiting once there's a UI worth shipping as an installable app. |
| Pure Python GUI (pygame / tkinter) | No browser involved, but tkinter has no efficient way to draw a 4096-cell grid and pygame has its own packaging story. Both make the later annotation UI (rich text panels, timelines) much harder than reusing HTML/CSS. |
| DOM-based grid instead of Canvas | Rejected specifically because a per-cell DOM grid re-rendered on every action is a plausible cause of the official site's own reported lag. |

## Consequences

- Gains: fast to build, cross-platform for free, Canvas keeps rendering cheap
  regardless of grid size, and the same stack carries forward into the
  annotation-tool milestone without a rewrite.
- Costs: requires the user to run a local server process and open a browser
  tab rather than double-clicking an app icon; not installable/distributable
  as a native app without later wrapping it.
- Does not fix: network latency to `three.arcprize.org` for real games. That
  latency is inherent to how ARC-AGI-3 works and is out of this project's
  control — the win here is removing client-side lag, not network lag.
