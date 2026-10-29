# Custom game "twins" (ARC Play, ARC-92). Put both avatars on their yellow targets at the same time.
# Actions: 1 up, 2 down, 3 left, 4 right.
#
# What a player has to discover: one input moves both avatars, but the right-hand twin goes the opposite way
# sideways (your left is its right) and the same way vertically; and when one twin is blocked by a wall the
# other still moves, which is how you line them up. Three levels.
from arcengine import ARCBaseGame, BlockingMode, Camera, GameAction, Level, Sprite

BACKGROUND, WALL, LEFT_FLOOR, RIGHT_FLOOR, TARGET = 0, 0, 5, 12, 4
LEFT_TWIN, RIGHT_TWIN = 7, 8
PIP_DONE, PIP_NOW, PIP_TODO = 13, 10, 5
ROOM_W = 8

# (left room, right room) for each row. P = a twin, T = its target.
MAPS = [
    [
        ("########", "########"),
        ("#....#.#", "#...#..#"),
        ("#......#", "#...#..#"),
        ("#....P.#", "#.....##"),
        ("#......#", "#.T..P.#"),
        ("#..#.T.#", "#...#..#"),
        ("########", "########"),
    ],
    [
        ("########", "########"),
        ("#....#.#", "#...#..#"),
        ("#...#..#", "#...#..#"),
        ("#...#..#", "#...T.##"),
        ("#P#...T#", "#.P....#"),
        ("#..#...#", "#...#..#"),
        ("########", "########"),
    ],
    [
        ("########", "########"),
        ("#..#...#", "#..P#..#"),
        ("#.....##", "#.##...#"),
        ("#..P...#", "#.##T..#"),
        ("##.T...#", "#..#...#"),
        ("#.#....#", "#.....##"),
        ("########", "########"),
    ],
]
MOVES = {
    GameAction.ACTION1: (0, -1),
    GameAction.ACTION2: (0, 1),
    GameAction.ACTION3: (-1, 0),
    GameAction.ACTION4: (1, 0),
}


def _px(color: int, x: int, y: int, name: str, layer: int = 0) -> Sprite:
    return Sprite(
        [[color]], name=name, x=x, y=y, layer=layer, blocking=BlockingMode.NOT_BLOCKED, collidable=False
    )


class Twins(ARCBaseGame):
    def __init__(self) -> None:
        levels = [
            Level(sprites=[], grid_size=(16, 16), name=f"level {i + 1}", data={"map": rows})
            for i, rows in enumerate(MAPS)
        ]
        super().__init__(
            game_id="twins",
            levels=levels,
            camera=Camera(width=16, height=16, background=BACKGROUND, letter_box=BACKGROUND),
            available_actions=[1, 2, 3, 4],
        )

    def on_set_level(self, level: Level) -> None:
        rows = level.get_data("map")
        self._oy = (15 - len(rows)) // 2
        self._walls = [set(), set()]
        self._targets = [(0, 0), (0, 0)]
        self._pos = [(0, 0), (0, 0)]
        self._sprites: list[Sprite] = []
        for y, pair in enumerate(rows):
            for side, row in enumerate(pair):
                floor = LEFT_FLOOR if side == 0 else RIGHT_FLOOR
                for x, ch in enumerate(row):
                    px, py = side * ROOM_W + x, self._oy + y
                    if ch == "#":
                        self._walls[side].add((x, y))
                        level.add_sprite(_px(WALL, px, py, f"wall{side}_{x}_{y}"))
                        continue
                    level.add_sprite(_px(floor, px, py, f"floor{side}_{x}_{y}"))
                    if ch == "T":
                        self._targets[side] = (x, y)
                        level.add_sprite(_px(TARGET, px, py, f"target{side}", layer=1))
                    elif ch == "P":
                        self._pos[side] = (x, y)
        for side, color in enumerate((LEFT_TWIN, RIGHT_TWIN)):
            x, y = self._pos[side]
            self._sprites.append(_px(color, side * ROOM_W + x, self._oy + y, f"twin{side}", layer=3))
            level.add_sprite(self._sprites[side])
        for i in range(len(MAPS)):
            color = PIP_DONE if i < self.level_index else PIP_NOW if i == self.level_index else PIP_TODO
            level.add_sprite(_px(color, 1 + 2 * i, 15, f"pip{i}"))

    def step(self) -> None:
        delta = MOVES.get(self.action.id)
        if delta is not None:
            for side in (0, 1):
                dx = delta[0] if side == 0 else -delta[0]  # the right-hand twin mirrors sideways moves
                x, y = self._pos[side]
                target = (x + dx, y + delta[1])
                if target not in self._walls[side]:
                    self._pos[side] = target
                    self._sprites[side].set_position(side * ROOM_W + target[0], self._oy + target[1])
            if self._pos[0] == self._targets[0] and self._pos[1] == self._targets[1]:
                self.next_level()
        self.complete_action()
