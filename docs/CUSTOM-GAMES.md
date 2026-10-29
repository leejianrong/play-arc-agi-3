# Custom games

Hand-authored puzzle games that produce `train-ok` annotated sessions (ADR-0009: only custom games are meant
to feed fine-tuning data; public games are `reference-only`). They live in `custom_games/` (tracked in git) and
are copied into `environment_files/` when the app starts, so they show up in the picker next to the real games,
tagged `custom`.

> **Playing them for data?** Don't read `custom_games/*/*.py` or the "spoilers" section below first. Each game
> file opens with a comment that says what a player has to discover, and your first contact with a game is where
> the reasoning is most visible and valuable.

## The five games

| id | Input | Levels (fewest moves) | In one line |
|----|-------|-----------------------|-------------|
| `slide` | arrows | 4, 7, 11 | movement on ice |
| `lamps` | clicks | 3, 5, 7 clicks | click puzzle on a grid of lamps |
| `keydoor` | arrows | 13, 22, 45 | collecting and spending items |
| `twins` | arrows | 7, 15, 20 | controlling two things at once |
| `crates` | arrows | 14, 27, 40 | pushing things onto targets |

Each has three levels of rising difficulty, a 16x16 picture, and level pips along the bottom. They were chosen to
exercise different kinds of reasoning (momentum, state that toggles, inventory, mirrored control, irreversible
moves) so the data is not about one trick.

## Adding a game

```text
custom_games/<id>/
  <id>.py          class <Id>(ARCBaseGame), logic in step(), levels as Level(sprites=[], data={...})
  metadata.json    {"game_id": "<id>", "title": "...", "tags": ["custom", ...], "class_name": "<Id>"}
```

Things that are not obvious, learned the hard way:

- **`class_name` is required** unless the id is exactly 4 characters. The toolkit takes the first four characters
  of the id as the class and file name (`slide` would be looked up as `Slid` in `slid.py`) unless `metadata.json`
  sets `class_name`. A test loads every game through the toolkit's own loader to catch this.
- **Ids must not collide** with the public catalog and must not contain `-` before the part you want classified:
  `data_policy.json` classifies by the text before the first `-`, and anything not listed as `public` is
  `train-ok`.
- **Build levels in `on_set_level`** from `level.get_data(...)` and add sprites there. The engine re-clones a
  clean level on reset, so a level built this way resets correctly. Calling `set_level` twice on the same level
  object stacks duplicate sprites (only a problem in tests).
- **Everything that matters must be visible on screen** (held items, progress). The solver and `--verify` key
  states by the rendered frame, and a human needs to see it anyway.
- Use `tests/helpers/solver.py` while designing: `solve(cls, level, dpad)` searches in the real engine (slow
  beyond ~20 moves); `tests/helpers/reference_solvers.py` has fast solvers that work on the map data.
- Add the game to `tests/unit/test_custom_games.py` (`GAMES`, `MIN_MOVES`, a solver, and a test per hidden rule),
  and to the `games` list in `scripts/e2e.py` if it plays with arrows or clicks.

Edits to `custom_games/` are picked up on the next start (`make run`, `make run-annotate`); the sync only
copies files that changed and never deletes anything in `environment_files/`.

## Quality bar

`make check` proves, by replaying an independent solver's answer through the real engine, that every level is
winnable, and pins the fewest-moves length so a level cannot quietly become trivial. `make e2e` plays level 1 of
every game in a real browser (keys, and mouse clicks for `lamps`), checks the canvas draws a real picture,
checks the session is labelled `train-ok`, and replays it with `--verify`. `RUN_SLOW_TESTS=1 make test` also
runs the generic engine search over the arrow games to confirm the reference lengths.

## Spoilers: what each game hides

Skip this until you have played them.

- `slide`: a move carries you until a wall stops you; the goal catches you mid-slide, so you do not need to
  stop on it.
- `lamps`: clicking a lamp also flips its four neighbours; every board is reachable from "all lit".
- `keydoor`: bright squares are keys, dark squares of the same hue are doors that only that key opens; a door
  uses the key up; picking up a second key throws the first away; the held key is shown bottom right.
- `twins`: one input moves both avatars, but the right-hand one mirrors sideways moves; a wall stops only the
  twin it blocks, which is how you line them up.
- `crates`: walking into a crate pushes it one square if the square behind is free; no pulling, so a crate in
  a corner is stuck (RESET restarts the level); a crate on a target turns green.
