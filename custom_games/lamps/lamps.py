# Custom game "lamps" (ARC Play, ARC-92). Light every lamp. Click a lamp to use it (action 6).
#
# What a player has to discover: a click does not only change the lamp you click. Three boards, 3x3, 4x4 and
# 5x5, each reachable from "all lit" by a handful of clicks, so each is solvable.
from arcengine import ARCBaseGame, BlockingMode, Camera, GameAction, Level, Sprite

BACKGROUND, ON, OFF = 0, 4, 12
PIP_DONE, PIP_NOW, PIP_TODO = 13, 10, 5

# (size, lamps row by row; 1 = lit). Cells are drawn `cell` pixels wide with a 1px gap.
BOARDS = [
    (3, [0, 1, 1, 0, 1, 0, 1, 1, 1]),
    (4, [1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 0, 0, 0, 0, 1, 0]),
    (5, [1, 0, 1, 1, 1, 0, 0, 0, 1, 0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 1, 1, 1, 0, 0]),
]
CELL = {3: 3, 4: 3, 5: 2}


def _block(color: int, x: int, y: int, size: int, name: str) -> Sprite:
    return Sprite(
        [[color] * size for _ in range(size)],
        name=name,
        x=x,
        y=y,
        blocking=BlockingMode.NOT_BLOCKED,
        collidable=False,
    )


class Lamps(ARCBaseGame):
    def __init__(self) -> None:
        levels = [
            Level(sprites=[], grid_size=(16, 16), name=f"level {i + 1}", data={"size": n, "lamps": lamps})
            for i, (n, lamps) in enumerate(BOARDS)
        ]
        super().__init__(
            game_id="lamps",
            levels=levels,
            camera=Camera(width=16, height=16, background=BACKGROUND, letter_box=BACKGROUND),
            available_actions=[6],
        )

    def on_set_level(self, level: Level) -> None:
        self._n = level.get_data("size")
        self._lit = list(level.get_data("lamps"))
        self._size = CELL[self._n]
        self._pitch = self._size + 1
        span = self._n * self._pitch - 1
        self._ox, self._oy = (16 - span) // 2, (15 - span) // 2
        self._sprites: dict[int, Sprite] = {}
        for i in range(self._n * self._n):
            self._draw(level, i)
        for i in range(len(BOARDS)):
            color = PIP_DONE if i < self.level_index else PIP_NOW if i == self.level_index else PIP_TODO
            level.add_sprite(_block(color, 1 + 2 * i, 15, 1, f"pip{i}"))

    def _draw(self, level: Level, i: int) -> None:
        if i in self._sprites:
            level.remove_sprite(self._sprites[i])
        x, y = i % self._n, i // self._n
        sprite = _block(
            ON if self._lit[i] else OFF,
            self._ox + x * self._pitch,
            self._oy + y * self._pitch,
            self._size,
            f"lamp{i}",
        )
        self._sprites[i] = sprite
        level.add_sprite(sprite)

    def _cell_at(self, display_x: int, display_y: int) -> int | None:
        grid = self.camera.display_to_grid(display_x, display_y)
        if grid is None:
            return None
        gx, gy = grid[0] - self._ox, grid[1] - self._oy
        if gx < 0 or gy < 0:
            return None
        cx, cy = gx // self._pitch, gy // self._pitch
        # The 1px gap between lamps belongs to no lamp.
        if cx >= self._n or cy >= self._n or gx % self._pitch >= self._size or gy % self._pitch >= self._size:
            return None
        return cy * self._n + cx

    def step(self) -> None:
        if self.action.id == GameAction.ACTION6:
            data = self.action.data or {}
            cell = self._cell_at(data.get("x", -1), data.get("y", -1))
            if cell is not None:
                x, y = cell % self._n, cell // self._n
                for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                    if 0 <= x + dx < self._n and 0 <= y + dy < self._n:
                        j = (y + dy) * self._n + x + dx
                        self._lit[j] ^= 1
                        self._draw(self.current_level, j)
                if all(self._lit):
                    self.next_level()
        self.complete_action()
