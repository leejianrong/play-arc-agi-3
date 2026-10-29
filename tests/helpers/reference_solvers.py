"""Fast reference solvers for the custom games, working on each level's map data (not on the game code).

Each returns the shortest list of actions (ints: 1 up, 2 down, 3 left, 4 right) that clears the level.
Tests replay that list through the real engine: if the game's rules or maps drift from what the solver
models, the replay stops winning. The generic engine search (solver.solve) is the slow ground truth.
"""

from __future__ import annotations

from collections import deque

DIRS = {1: (0, -1), 2: (0, 1), 3: (-1, 0), 4: (1, 0)}


def _find(rows, ch):
    return next(((x, y) for y, r in enumerate(rows) for x, c in enumerate(r) if c == ch), None)


def _cells(rows, ch):
    return {(x, y) for y, r in enumerate(rows) for x, c in enumerate(r) if c == ch}


def slide(rows: list[str]) -> list[int] | None:
    walls, goal, start = _cells(rows, "#"), _find(rows, "G"), _find(rows, "P")
    queue, seen = deque([(start, [])]), {start}
    while queue:
        pos, path = queue.popleft()
        for action, (dx, dy) in DIRS.items():
            x, y = pos
            while (x + dx, y + dy) not in walls:
                x, y = x + dx, y + dy
                if (x, y) == goal:
                    return [*path, action]
            if (x, y) != pos and (x, y) not in seen:
                seen.add((x, y))
                queue.append(((x, y), [*path, action]))
    return None


def keydoor(rows: list[str]) -> list[int] | None:
    walls, exit_, start = _cells(rows, "#"), _find(rows, "E"), _find(rows, "P")
    keys = {(x, y): c for y, r in enumerate(rows) for x, c in enumerate(r) if c in "rbg"}
    doors = {(x, y): c.lower() for y, r in enumerate(rows) for x, c in enumerate(r) if c in "RBG"}
    first = (start, None, frozenset(), frozenset())  # position, held key, keys taken, doors opened
    queue, seen = deque([(first, [])]), {first}
    while queue:
        (pos, held, taken, opened), path = queue.popleft()
        if pos == exit_:
            return path
        for action, (dx, dy) in DIRS.items():
            nxt = (pos[0] + dx, pos[1] + dy)
            if nxt in walls:
                continue
            nheld, ntaken, nopened = held, taken, opened
            if nxt in doors and nxt not in opened:
                if held != doors[nxt]:
                    continue
                nopened, nheld = opened | {nxt}, None
            if nxt in keys and nxt not in taken:
                nheld, ntaken = keys[nxt], taken | {nxt}
            state = (nxt, nheld, ntaken, nopened)
            if state not in seen:
                seen.add(state)
                queue.append((state, [*path, action]))
    return None


def twins(pairs: list[tuple[str, str]]) -> list[int] | None:
    left = [p[0] for p in pairs]
    right = [p[1] for p in pairs]
    wl, wr = _cells(left, "#"), _cells(right, "#")
    a0, ta, b0, tb = _find(left, "P"), _find(left, "T"), _find(right, "P"), _find(right, "T")
    queue, seen = deque([((a0, b0), [])]), {(a0, b0)}
    while queue:
        (a, b), path = queue.popleft()
        if path and a == ta and b == tb:
            return path
        for action, (dx, dy) in DIRS.items():
            na = (a[0] + dx, a[1] + dy)
            nb = (b[0] - dx, b[1] + dy)  # the right twin mirrors sideways
            state = (na if na not in wl else a, nb if nb not in wr else b)
            if state not in seen:
                seen.add(state)
                queue.append((state, [*path, action]))
    return None
