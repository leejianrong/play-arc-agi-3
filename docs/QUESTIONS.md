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
| Q3 | Record actions-only vs full frame+action every step? | DECIDED | Full frame + action + state every step, one JSONL line per step — superseded by Q21/ADR-0005: now a per-session choice (off/lean/full), not a fixed format | ADR-0003, ADR-0005 |
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
| Q21 | Recordings piled up unbounded and full mode is huge (25MB+ sessions seen) — default behavior and detail-level options? | DECIDED | Default OFF. Picker gets an Off/Lean/Full control; Lean omits the frame grid, viable now because games are confirmed deterministic (checked `arcengine` for any randomness source — found none that affects gameplay), so a lean recording's frames are reconstructable later via local replay. | ADR-0005 |
| Q22 | UI style for the record on/off/detail choice: checkbox, per-game confirm dialog, mid-session toggle, or a control near the picker? | DECIDED | A single `Off/Lean/Full` dropdown in the picker header, default Off — one persistent control, no per-click interruption. | ADR-0005, frontend redesign |
| Q23 | Thumbnails per game in the picker — render each game's real first frame, or something cheaper? | DECIDED | A deterministic per-`game_id` swatch (`frontend/identicon.js`): a hash-seeded sparse pattern drawn from the real ARC palette, not an actual preview. Rendering real first frames would mean downloading every listed game's source just to populate the picker — the identicon costs nothing and needs no network. | frontend redesign |
| Q24 | Speech-to-text engine? (F1) | DECIDED | Local `faster-whisper` `small.en` behind a `Transcriber` protocol; typed notes always available | ADR-0006 |
| Q25 | Mic behaviour? (F2) | DECIDED | Continuous capture with VAD and a mute key, not hold-to-talk | ADR-0006 |
| Q26 | How are phases labelled? (F3) | DECIDED | Explicit: starts `observe` each level, first game action auto-switches to `probe`, keys `1-5` for the rest; never blocks input | ADR-0008 |
| Q27 | Hypothesis structure? (F4) | DECIDED | Free text primary, plus sparse `H`/`Y`/`N` tags with stable IDs, mapping onto `solve-arc-agi-3`'s ledger | ADR-0008 |
| Q28 | Milestone scope? (F5) | DECIDED | Capture plus a timeline CLI with replay verification; no in-app viewer, no exporter | ADR-0007, PLAN §Scope |
| Q29 | Which games get annotated? (F6, "your call") | DECIDED | `heldout` (9 games, annotation refused), `reference-only` (other public games), `train-ok` (custom envs) | ADR-0009 |
| Q30 | Where do annotations live? | ASSUMED | Sidecar `*.annotations.jsonl` aligned by step index and time; `Recorder` only gains `frame_sha256` (schema 3) | ADR-0007 |
| Q31 | Frame fidelity and audio retention for annotated sessions? | ASSUMED | At least Lean (Off promoted to Lean); raw opus audio kept locally and gitignored, `KEEP_AUDIO=0` to disable | ADR-0006, ADR-0007 |
| Q32 | Keys that don't clash with the game? | ASSUMED | `T` focus note box, `1-5` phases, `H/Y/N` hypotheses, `M` mute | ADR-0008 |
| Q33 | Initial held-out list? | ASSUMED | Every third public game in sorted order; should be reconciled with the solver's eval split | ADR-0009 |
| Q34 | Annotation failure behaviour? | ASSUMED | Mic, model or `/ws/audio` failure shows a banner and play, recording and typed notes continue; truncated sidecars stay readable | PLAN §Open risks, SLICES V3 |
| Q35 | Sensitive data in annotations? | ASSUMED | Voice audio and transcripts are local only and gitignored; no API key in any annotation file; no cloud STT | ADR-0006 |
| Q36 | What is one training example? | DECIDED | A decision point: state (observation text, ledger, history) in; reasoning, ledger ops and the action chunk out; silent chunks are not examples | ADR-0010 |
| Q37 | Primary interface for agent play? (F1) | DECIDED | MCP server first; Playwright stays the UI test harness (and `@playwright/mcp` can be used for UI QA without our code) | ADR-0011 |
| Q38 | What does the agent see? (F2) | DECIDED | Compact native-resolution text by default, a PNG on request; the encoder is a first version of ARC-87's | ADR-0011 |
| Q39 | Shared live session with the agent, or standalone? (F3) | DECIDED | Revised 2026-10-30 on user input: MCP lives inside the app, sessions are agent-owned with a read-only browser spectator view; shared two-writer control deferred | ADR-0011 |
| Q40 | How is agent play labelled? (F4) | DECIDED | `data_use: agent`, `actor: agent`, `agent.` file prefix; never human training data; held-out needs `allow_heldout` | ADR-0012 |
| Q41 | Which tools, and how does the agent record its reasoning? | ASSUMED | Game tools plus `note`, `hypothesis_add`, `hypothesis_verdict`, `set_phase`, and an optional `thought` on `act`; same annotation events as a human | ADR-0011 |
| Q42 | How is runaway play prevented? | ASSUMED | Per-session action budget, default 300 (reset counts); exceeding it is an error and the session stays readable | ADR-0011 |
| Q43 | Real games and spoilers? | ASSUMED | Real games available like in the app; blind play is a convention (subagent told not to read `custom_games/`), not a sandbox | ADR-0011 |
| Q44 | How is the server shipped? | ASSUMED | `mcp` as a normal dependency, mounted at `/mcp` (streamable HTTP), `.mcp.json` entry `arc-play` of type http; `make run` must be up; Claude Code needs one restart to load it | ADR-0011 |
| Q45 | Failure behaviour for agents? | ASSUMED | MCP tool errors with specific messages (unknown game, no session, action not offered, budget exceeded, held-out refused); never a crash | ADR-0011, ADR-0012 |
| Q46 | Our own Playwright driver for agent play? | DEFERRED | The existing `make e2e` harness and `@playwright/mcp` cover UI checks; build a UI-driving library only if live co-play (Q39) is picked up | n/a |

## Coverage

| Category | Covered by |
|----------|-----------|
| Primary user and actors | Q4, Q25, Q40 |
| Scope boundary | Q2, Q5, Q28 |
| Data model and identity | Q3, Q14, Q26, Q27, Q30, Q36 |
| State and storage | Q6, Q7, Q29, Q31 |
| Concurrency and conflict | Q7, Q39 |
| Interfaces and contracts | Q1, Q8, Q9, Q10, Q11, Q32, Q37, Q38, Q41 |
| Failure behaviour | Q15, Q34, Q42, Q45 |
| External dependencies | Q8, Q12, Q18, Q24, Q44 |
| Runtime and deployment | Q1, Q13 |
| Measurable success | Q16 |
| Security and secrets | Q12, Q35, Q43 |
| Versioning and migration | Q14 |
