# Custom game "slide" (ARC Play, ARC-92). The floor is ice: a move carries you until something stops you.
# Reach the goal: you fall in when you pass over it. Actions: 1 up, 2 down, 3 left, 4 right.
#
# What a player has to discover: moves are not one cell long, walls are the only brakes, and the goal
# catches you mid-slide. Three levels, each needing a different use of the walls.
from arcengine import ARCBaseGame, BlockingMode, Camera, GameAction, Level, Sprite

BACKGROUND, WALL, ICE, GOAL, PLAYER = 0, 5, 12, 4, 7
PIP_DONE, PIP_NOW, PIP_TODO = 13, 10, 5

MAPS = [
    [
        "#########",
        "#...#..##",
        "#.#P##..#",
        "#......G#",
        "##...#..#",
        "#.....###",
        "#########",
    ],
    [
        "###########",
        "#.#...G...#",
        "#.#.....#.#",
        "#..#..##.##",
        "#.#.......#",
        "#.........#",
        "#.....#.P.#",
        "###########",
    ],
    [
        "#############",
        "#.....P..#..#",
        "###...##..#.#",
        "#.#......#.##",
        "#....#......#",
        "#..#.....G..#",
        "#..#..#....##",
        "#############",
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


class Slide(ARCBaseGame):
    def __init__(self) -> None:
        levels = [
            Level(sprites=[], grid_size=(16, 16), name=f"level {i + 1}", data={"map": rows})
            for i, rows in enumerate(MAPS)
        ]
        super().__init__(
            game_id="slide",
            levels=levels,
            camera=Camera(width=16, height=16, background=BACKGROUND, letter_box=BACKGROUND),
            available_actions=[1, 2, 3, 4],
        )

    def on_set_level(self, level: Level) -> None:
        rows = level.get_data("map")
        self._ox, self._oy = (16 - len(rows[0])) // 2, (15 - len(rows)) // 2
        self._walls: set[tuple[int, int]] = set()
        self._goal = (0, 0)
        self._pos = (0, 0)
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                px, py = self._ox + x, self._oy + y
                if ch == "#":
                    self._walls.add((x, y))
                    level.add_sprite(_px(WALL, px, py, f"wall{x}_{y}"))
                    continue
                level.add_sprite(_px(ICE, px, py, f"ice{x}_{y}"))
                if ch == "G":
                    self._goal = (x, y)
                    level.add_sprite(_px(GOAL, px, py, "goal", layer=1))
                elif ch == "P":
                    self._pos = (x, y)
        self._player = _px(PLAYER, self._ox + self._pos[0], self._oy + self._pos[1], "player", layer=2)
        level.add_sprite(self._player)
        for i in range(len(MAPS)):
            color = PIP_DONE if i < self.level_index else PIP_NOW if i == self.level_index else PIP_TODO
            level.add_sprite(_px(color, 1 + 2 * i, 15, f"pip{i}"))

    def step(self) -> None:
        delta = MOVES.get(self.action.id)
        if delta is not None:
            x, y = self._pos
            reached = False
            while (x + delta[0], y + delta[1]) not in self._walls:
                x, y = x + delta[0], y + delta[1]
                if (x, y) == self._goal:
                    reached = True
                    break
            self._pos = (x, y)
            self._player.set_position(self._ox + x, self._oy + y)
            if reached:
                self.next_level()
        self.complete_action()
