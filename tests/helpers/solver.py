"""Breadth-first solver for custom games, played through the real arcengine.

Used by tests (every level of every custom game must be winnable, and not trivially) and while designing
levels. It deep-copies the game per node and keys states by the rendered frame, so any hidden state a game
keeps must also be visible on screen (which is also what a human player needs).
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
from collections import deque
from collections.abc import Callable
from pathlib import Path

from arcengine import ActionInput, GameAction, GameState

CUSTOM_DIR = Path(__file__).resolve().parent.parent.parent / "custom_games"

Move = tuple[int, int | None, int | None]  # (action id, x, y) with x/y only for ACTION6 clicks


def load_game_class(game_id: str, directory: Path = CUSTOM_DIR):
    path = directory / game_id / f"{game_id}.py"
    spec = importlib.util.spec_from_file_location(f"custom_{game_id}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, game_id.capitalize())


_BY_ID = {a.value: a for a in GameAction}


def apply(game, move: Move):
    action_id, x, y = move
    data = {"x": x, "y": y} if action_id == 6 else {}
    return game.perform_action(ActionInput(id=_BY_ID[action_id], data=data))


def _key(game, frame) -> bytes:
    h = hashlib.sha1()
    h.update(str(game.level_index).encode())
    for layer in frame.frame[-1:] or [[]]:
        h.update(repr(layer).encode())
    return h.digest()


def solve(
    game_cls,
    level_index: int,
    moves_for: Callable[[object], list[Move]],
    max_nodes: int = 400_000,
) -> list[Move] | None:
    """Shortest move list that completes `level_index`, or None if none is found within the node budget."""
    root = game_cls()
    if level_index != 0:  # the constructor already set level 0; set_level twice would stack sprites
        root.set_level(level_index)
    start_score = root._score
    seen: set[bytes] = set()
    queue: deque[tuple[object, list[Move]]] = deque([(root, [])])
    nodes = 0
    while queue:
        game, path = queue.popleft()
        for move in moves_for(game):
            nxt = copy.deepcopy(game)
            frame = apply(nxt, move)
            nodes += 1
            if frame.levels_completed > start_score or frame.state == GameState.WIN:
                return [*path, move]
            if frame.state == GameState.GAME_OVER or not frame.frame:
                continue
            key = _key(nxt, frame)
            if key in seen:
                continue
            seen.add(key)
            queue.append((nxt, [*path, move]))
            if nodes > max_nodes:
                return None
    return None


def dpad(game) -> list[Move]:
    """The four direction actions."""
    return [(1, None, None), (2, None, None), (3, None, None), (4, None, None)]


def lights_out_presses(n: int, lit: list[int]) -> list[int]:
    """Fewest lamps to click (row-major indexes) to light a lights-out board, by GF(2) elimination.
    Raises ValueError if the board is unsolvable."""
    import itertools

    cells = n * n
    matrix = []
    for i in range(cells):
        row = [0] * cells
        x, y = i % n, i // n
        for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            if 0 <= x + dx < n and 0 <= y + dy < n:
                row[(y + dy) * n + x + dx] = 1
        matrix.append(row)
    rows = [matrix[i][:] + [1 - lit[i]] for i in range(cells)]
    pivots, r = [], 0
    for c in range(cells):
        pr = next((i for i in range(r, cells) if rows[i][c]), None)
        if pr is None:
            continue
        rows[r], rows[pr] = rows[pr], rows[r]
        for i in range(cells):
            if i != r and rows[i][c]:
                rows[i] = [a ^ b for a, b in zip(rows[i], rows[r], strict=True)]
        pivots.append(c)
        r += 1
    if any(not any(row[:cells]) and row[cells] for row in rows):
        raise ValueError("unsolvable board")
    free = [c for c in range(cells) if c not in pivots]
    best = None
    for bits in itertools.product((0, 1), repeat=len(free)):
        p = [0] * cells
        for c, v in zip(free, bits, strict=True):
            p[c] = v
        for row_i, c in enumerate(pivots):
            p[c] = rows[row_i][cells] ^ (sum(rows[row_i][f] & p[f] for f in free) & 1)
        presses = [i for i, v in enumerate(p) if v]
        if best is None or len(presses) < len(best):
            best = presses
    return best


def crates_solution(rows: list[str]) -> list[int] | None:
    """Shortest list of direction actions that covers every target, by BFS on (player, crates).

    Independent of the game's code (it reads the level's map), so replaying its answer through the engine
    checks the game rather than itself. Too many states for the generic engine search at 3 crates."""
    walls, crates, targets, player = set(), set(), set(), (0, 0)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == "#":
                walls.add((x, y))
            elif ch == "C":
                crates.add((x, y))
            elif ch == "T":
                targets.add((x, y))
            elif ch == "P":
                player = (x, y)
    dirs = {1: (0, -1), 2: (0, 1), 3: (-1, 0), 4: (1, 0)}
    start = (player, frozenset(crates))
    queue: deque[tuple[tuple, list[int]]] = deque([(start, [])])
    seen = {start}
    while queue:
        (pos, cs), path = queue.popleft()
        if cs == targets:
            return path
        for action, (dx, dy) in dirs.items():
            nxt = (pos[0] + dx, pos[1] + dy)
            if nxt in walls:
                continue
            ncs = cs
            if nxt in cs:
                beyond = (nxt[0] + dx, nxt[1] + dy)
                if beyond in walls or beyond in cs:
                    continue
                ncs = (cs - {nxt}) | {beyond}
            state = (nxt, ncs)
            if state not in seen:
                seen.add(state)
                queue.append((state, [*path, action]))
    return None
