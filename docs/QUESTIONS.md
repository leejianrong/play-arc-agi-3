# Questions

Statuses: `DECIDED` (user answered) · `ASSUMED` (default taken, correct it if
wrong) · `FORK` (waiting on the user) · `DEFERRED` (not needed this milestone).

## Open forks

_empty — round closed_

## Register

| ID | Question | Status | Answer or default | Landed |
|----|----------|--------|--------------------|--------|
| Q1 | Local web app vs native desktop wrapper vs pure-Python GUI? | DECIDED | Local web app: FastAPI + WebSocket backend, vanilla JS/Canvas frontend on localhost | ADR-0001 |
| Q2 | Support locally-authored custom puzzle envs (`arc_agi` offline mode) in addition to the real competition games? | DECIDED | Yes, both — sequenced as slice V2 behind the same abstraction so V1 (real games) ships first | ADR-0002, SLICES V2 |
| Q3 | Record actions-only vs full frame+action every step? | DECIDED | Full frame + action + state every step, one JSONL line per step | ADR-0003 |
| Q4 | Who is this for? | ASSUMED | Single local human user (Jian), playing solo. No multi-user, no auth beyond the ARC API key. | PLAN §Users |
| Q5 | Is annotation / thought-process capture in this milestone? | ASSUMED | No — explicitly out of scope for MVP, stated by the user as "eventually." Recording schema (Q3) is designed so it can be added without a data migration. | PLAN §Scope |
| Q6 | Storage: flat files vs database? | ASSUMED | Flat JSONL files under `recordings/`, one file per session. Single user, no concurrent writers, and files are human-diffable/greppable — matches the pattern the official ARC-AGI-3-Agents repo already uses. | ADR-0003 |
| Q7 | Concurrency: multiple simultaneous sessions? | ASSUMED | One active session per running server process. A second browser tab is a known limitation, not handled gracefully in MVP. | PLAN §Implementation decisions |
| Q8 | Depend on the official `ARC-AGI-3-Agents` framework, or write a thin client? | ASSUMED | Not the agents framework (LangGraph/AgentOps/swarm surface area irrelevant here) — but superseded on the "thin client" half: `arc_agi.Arcade` directly, for real games too, not just custom envs. | ADR-0004 |
| Q9 | Rendering: DOM grid vs Canvas? | ASSUMED | HTML5 Canvas. A 64×64 per-cell DOM grid is a likely cause of the official site's reported lag; Canvas avoids it. | ADR-0001 |
| Q10 | Keyboard/mouse control scheme? | ASSUMED | Arrows/WASD → ACTION1-4, Space/Enter → ACTION5, click on grid → ACTION6 (x,y scaled to the 0-63 frame), Backspace → ACTION7 (undo, when `available_actions` includes it), R → RESET. Easy to remap later; not load-bearing. | PLAN §Affordances |
| Q11 | Game catalog: hardcoded list vs fetched dynamically? | ASSUMED | Fetched dynamically from the API's list-games endpoint each session start; local custom envs discovered by scanning `environment_files/`. | SLICES V1, V2 |
| Q12 | Secrets handling? | ASSUMED | `ARC_API_KEY` in a gitignored `.env`, loaded server-side only, never sent to the frontend, never written into recordings or logs. Server binds `127.0.0.1` only. | PLAN §Security |
| Q13 | Runtime/deployment? | ASSUMED | Single command (`make run`) starts a local uvicorn server and opens the default browser. No packaging/installer for MVP. Port defaults to 8000 via `PORT`, but auto-falls back to an OS-assigned free port if that's taken — confirmed necessary in practice (this laptop already has an unrelated Docker service bound to 8000). | PLAN §Shape |
| Q14 | Versioning of the recording schema? | ASSUMED | A `schema_version` field on every recorded line, starting at 1, so a future annotation tool can branch on old recordings without a migration step. | ADR-0003 |
| Q15 | Failure behaviour on API errors / missing key / local env crash? | ASSUMED | Missing `ARC_API_KEY` → clear startup error, server refuses to start. Remote API errors (4xx/timeout) → surfaced as a UI banner, session state and recording preserved, retry possible. Local custom-env Python exceptions → logged and surfaced in the UI, do not crash the server. | PLAN §Affordances (Error banner), SLICES V1 §End-to-end |
| Q16 | Measurable success for MVP? | ASSUMED | A human can: pick a real game, play at least 20 actions via keyboard/mouse with the grid updating within one render frame of each response, and end up with a recording file whose line count equals actions taken + 1 (initial reset), each line valid JSON with a `frame` matching what was shown on screen. | SLICES V1 §End-to-end |
| Q17 | Color palette for rendering the 0-15 cell values? | ASSUMED | Fixed 16-color lookup table matching ARC-AGI's established visual convention; exact hex values confirmed empirically against a real game during slice 1 build (low-risk, immediately visible if wrong). | Open risk, SLICES V1 |
| Q18 | Are the three dependencies' licences and offline story checked? | DECIDED | `arcprize/ARC-AGI` (the `arc_agi` package) is MIT-licensed and runs locally by design. FastAPI is MIT, httpx is BSD-3-Clause — both standard, permissive, no network requirement of their own. All three are safe to depend on and none constrain redistribution. | ADR-0002 |
| Q19 | Real V1 usage reported it's "still laggy" and hit a raw 400 error mid-session — root cause and fix? | DECIDED | Root cause: `RemoteGameSource` called the remote API per action (the actual lag source) and its guid-based session lookup went stale after ARC's 15-minute scorecard idle-timeout (the actual 400 cause). Fix: retire `RemoteGameSource`, run real games locally via `arc_agi`'s own `NORMAL` mode — user confirmed "yes, do it now." | ADR-0004 |
| Q20 | Can the real games be downloaded and run fully locally at all? | DECIDED | Yes — reverses Q-implicit assumption baked into ADR-0002's original Context. `arc_agi.Arcade(operation_mode=OperationMode.NORMAL)`, the package's own default, downloads a game's real Python source once (`GET /api/games/{game_id}-{version}/source`) and executes every action after that locally, in-process. Measured at 0.5ms/action locally vs. a full HTTP round trip before. | ADR-0004 |

## Coverage

| Category | Covered by |
|----------|-----------|
| Primary user and actors | Q4 |
| Scope boundary | Q2, Q5 |
| Data model and identity | Q3, Q14 |
| State and storage | Q6, Q7 |
| Concurrency and conflict | Q7 |
| Interfaces and contracts | Q1, Q8, Q9, Q10, Q11 |
| Failure behaviour | Q15 |
| External dependencies | Q8, Q12, Q18 |
| Runtime and deployment | Q1, Q13 |
| Measurable success | Q16 |
| Security and secrets | Q12 |
| Versioning and migration | Q14 |
