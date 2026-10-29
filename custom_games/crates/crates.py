# Custom game "crates" (ARC Play, ARC-92). Cover every yellow target with a crate.
# Actions: 1 up, 2 down, 3 left, 4 right; RESET restarts the level if you box a crate in.
#
# What a player has to discover: walking into a crate pushes it one square, but only if the square behind it
# is free (a wall or another crate stops it, and you stay put); crates cannot be pulled, so a crate pushed into
# a corner is stuck for good; a crate on a target turns green. Three levels with one, two and three crates.
from arcengine import ARCBaseGame, BlockingMode, Camera, GameAction, Level, Sprite

BACKGROUND, WALL, FLOOR, TARGET, CRATE, CRATE_HOME, PLAYER = 0, 0, 5, 4, 7, 3, 10
PIP_DONE, PIP_NOW, PIP_TODO = 13, 10, 5

MAPS = [
    [
        "########",
        "#....#.#",
        "#.#C.#P#",
        "#...T..#",
        "#......#",
        "#.....##",
        "########",
    ],
    [
        "#########",
        "#T......#",
        "##....#.#",
        "#T...P..#",
        "#...CC..#",
        "#....#..#",
        "#########",
    ],
    [
        "##########",
        "#.#...#..#",
        "#...#....#",
        "#.#.#CTT.#",
        "#..P..CC.#",
        "#......###",
        "#...T#...#",
        "##########",
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


class Crates(ARCBaseGame):
    def __init__(self) -> None:
        levels = [
            Level(sprites=[], grid_size=(16, 16), name=f"level {i + 1}", data={"map": rows})
            for i, rows in enumerate(MAPS)
        ]
        super().__init__(
            game_id="crates",
            levels=levels,
            camera=Camera(width=16, height=16, background=BACKGROUND, letter_box=BACKGROUND),
            available_actions=[1, 2, 3, 4],
        )

    def on_set_level(self, level: Level) -> None:
        rows = level.get_data("map")
        self._ox, self._oy = (16 - len(rows[0])) // 2, (15 - len(rows)) // 2
        self._walls: set[tuple[int, int]] = set()
        self._targets: set[tuple[int, int]] = set()
        self._crates: set[tuple[int, int]] = set()
        self._crate_sprites: list[Sprite] = []
        self._pos = (0, 0)
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                px, py = self._ox + x, self._oy + y
                if ch == "#":
                    self._walls.add((x, y))
                    level.add_sprite(_px(WALL, px, py, f"wall{x}_{y}"))
                    continue
                level.add_sprite(_px(FLOOR, px, py, f"floor{x}_{y}"))
                if ch == "T":
                    self._targets.add((x, y))
                    level.add_sprite(_px(TARGET, px, py, f"target{x}_{y}", layer=1))
                elif ch == "C":
                    self._crates.add((x, y))
                elif ch == "P":
                    self._pos = (x, y)
        self._player = _px(PLAYER, self._ox + self._pos[0], self._oy + self._pos[1], "player", layer=3)
        level.add_sprite(self._player)
        self._draw_crates()
        for i in range(len(MAPS)):
            color = PIP_DONE if i < self.level_index else PIP_NOW if i == self.level_index else PIP_TODO
            level.add_sprite(_px(color, 1 + 2 * i, 15, f"pip{i}"))

    def _draw_crates(self) -> None:
        level = self.current_level
        for sprite in self._crate_sprites:
            level.remove_sprite(sprite)
        self._crate_sprites = []
        for n, (x, y) in enumerate(sorted(self._crates)):
            color = CRATE_HOME if (x, y) in self._targets else CRATE
            sprite = _px(color, self._ox + x, self._oy + y, f"crate{n}", layer=2)
            self._crate_sprites.append(sprite)
            level.add_sprite(sprite)

    def step(self) -> None:
        delta = MOVES.get(self.action.id)
        if delta is not None:
            target = (self._pos[0] + delta[0], self._pos[1] + delta[1])
            if target not in self._walls:
                moved = True
                if target in self._crates:
                    beyond = (target[0] + delta[0], target[1] + delta[1])
                    if beyond in self._walls or beyond in self._crates:
                        moved = False
                    else:
                        self._crates.remove(target)
                        self._crates.add(beyond)
                        self._draw_crates()
                if moved:
                    self._pos = target
                    self._player.set_position(self._ox + target[0], self._oy + target[1])
                    if self._crates == self._targets:
                        self.next_level()
        self.complete_action()
