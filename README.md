# ARC Play

A local client for playing real [ARC-AGI-3](https://three.arcprize.org) games. The
hosted web UI is slow because it round-trips to ARC's servers on every move; this app
downloads a game's real source once (via ARC's own `arc_agi` toolkit) and runs every
action after that locally, in-process. Every move is recorded to a JSONL file, so a
future annotation tool has something to load.

Personal, single-user, local-only. Not published, not deployed anywhere.

## Quick start

You need [uv](https://docs.astral.sh/uv/) and an ARC API key from
[arcprize.org/platform](https://arcprize.org/platform).

```sh
cp .env.example .env        # then put your real ARC_API_KEY in .env
make run
```

`make run` prints the URL to open (it doesn't open a browser for you — see
[Notes](#notes)). Pick a game from the list and play with keyboard/mouse:

- Arrows / WASD — move (ACTION1-4)
- Space / Enter — act (ACTION5)
- Click on the grid — target (ACTION6)
- Backspace — undo (ACTION7, when the game offers it)
- R — reset

## Configuration

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `ARC_API_KEY` | yes | — | From [arcprize.org/platform](https://arcprize.org/platform). Server only; never sent to the frontend. |
| `PORT` | no | `8000` | Preferred port. If taken, `make run` picks a free one and tells you. |
| `RECORDINGS_DIR` | no | `recordings/` | Where session recordings land. |
| `ENVIRONMENTS_DIR` | no | `environment_files/` | Where downloaded game source is cached, and where hand-authored custom games go. |

A game's source is downloaded once per game and cached under `environment_files/`
(gitignored) — replaying a game you've already played needs no network at all.
Recordings land under `recordings/` (also gitignored): one JSONL file per session,
one line per move, full frame included — see
[docs/adr/0003-recording-format.md](docs/adr/0003-recording-format.md).

## Everyday commands

```sh
make install   # sync dependencies
make run       # start the app
make test      # fast test layer: pytest + node --test, no infra needed
make lint      # ruff over backend/, main.py, tests/
make check     # lint + test — what the pre-push hook runs
make hooks     # install the pre-push hook (one-time; not tracked by git itself)
make clean     # remove caches and the virtualenv
```

## How it's built

The design record lives in `docs/`, not here:

- [`docs/PLAN.md`](docs/PLAN.md) — problem, scope, requirements, shape
- [`docs/adr/`](docs/adr/) — the individual decisions and why, including the
  correction in [ADR-0004](docs/adr/0004-local-execution-via-arc-agi-toolkit.md)
  that made this actually responsive
- [`docs/SLICES.md`](docs/SLICES.md) — what's built vs. planned
- [`docs/QUESTIONS.md`](docs/QUESTIONS.md) — the full decision register

For how an agent should work in this repo, see [`CLAUDE.md`](CLAUDE.md).

## Notes

- `make run` doesn't auto-open a browser. It used to, but in a headless/WSL/container
  environment with no real GUI browser, `webbrowser.open()` can fall through to a
  full-screen text browser and take over the terminal — worth knowing if you ever
  re-add it.
- Downloaded game source under `environment_files/` is ARC's content, fetched with
  your own API key — it's gitignored and not meant to be redistributed.
