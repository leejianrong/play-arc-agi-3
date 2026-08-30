# AGENTS.md

## WHAT

ARC Play: a personal, single-user, local-only web app for playing real ARC-AGI-3
games. FastAPI + one WebSocket endpoint (`backend/server.py`) drives game execution
and recording; a vanilla JS/Canvas frontend (`frontend/`) renders and captures
input. `uv` manages the Python env; the Makefile is the command surface.

```
backend/
  server.py            WebSocket session loop: start/action -> GameSource -> Recorder
  config.py            ARC_API_KEY loading
  recorder.py          JSONL session recorder (ADR-0003)
  game_sources/
    base.py            GameSource protocol, FrameData, GameState/ActionId
    arcade.py           ArcadeGameSource -- the one execution path (see HOW)
frontend/               index.html, app.js, input_mapping.js, palette.js -- no build step
docs/                   PLAN.md, adr/, SLICES.md, QUESTIONS.md -- the design record
tests/
  unit/                 no infra; arcade tests run a real fixture game (tests/fixtures/)
  integration/          WebSocket loop against a stub GameSource
```

## WHY

The hosted ARC-AGI-3 web UI is slow. This app fixes that by running games locally
instead of round-tripping to ARC's API per move — see
`docs/adr/0004-local-execution-via-arc-agi-toolkit.md` for the full story, including
what got tried first and reverted.

## HOW

**Commands** — `make help` lists them all; the ones that matter:

```sh
make run     # start the app, prints the URL (doesn't auto-open a browser -- see README)
make check   # lint + test -- run this before considering any change done
make hooks   # one-time: installs make check as .git/hooks/pre-push
```

**Trust the code over these docs where they disagree**, and fix the doc.

### Game execution: one path, not two

`ArcadeGameSource` (`backend/game_sources/arcade.py`) wraps `arc_agi.Arcade` and is
the *only* way this app talks to a game — `OperationMode.NORMAL` for real games
(downloads a game's source once, then every action executes locally, in-process),
`OperationMode.OFFLINE` for hand-authored custom envs. **Do not add a per-action
remote HTTP client.** `RemoteGameSource` was exactly that, and was deleted in
ADR-0004 because it was the actual cause of reported lag — every action round-tripped
to `three.arcprize.org`. If responsiveness ever regresses, suspect whatever bypassed
local execution, not the frontend.

Because of this, `FrameData.source` (and `GameSourceKind`) is always `"local"` now.
It's kept as a field for a hypothetical third execution path, not because two are
in use.

`arcengine`'s own `perform_action()` returns an empty frame (`frame=[]`) for any
non-RESET action once a game is already `WIN`/`GAME_OVER` — that's normal, not a
failure. `ArcadeGameSource` handles this by reusing the last real frame
(`_last_frame`); don't reintroduce a check that treats an empty frame as an error.

### Data that must never be committed

- `.env` (`ARC_API_KEY`) — never log it, never write it into a recording, never
  put it in a commit message or test fixture.
- `recordings/` and `environment_files/` — gitignored caches (session recordings;
  downloaded/cached game source). Both regenerate from a live run; neither belongs
  in git.

### Design docs

Architectural decisions live in `docs/adr/*.md`, one file per decision, numbered
sequentially. Before making a change that reverses or extends one (game execution,
recording format, the local-web-app stack choice), read the relevant ADR first —
they carry the "why" and the alternatives already rejected, so you don't re-litigate
a settled question. Add a new ADR for a genuinely new architectural decision; don't
edit history into an old one. `docs/PLAN.md` and `docs/SLICES.md` track scope and
what's built vs. planned — update them when either changes materially.

### No CI yet

Solo, local-only, no git remote. `make check` (and the pre-push hook it installs)
is the whole gate. If this repo ever gets a remote, revisit `dev-playbook`'s CI/PR
checklist — none of it applies yet.
