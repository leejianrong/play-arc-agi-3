# Custom game "keydoor" (ARC Play, ARC-92). Walk to the yellow exit. Actions: 1 up, 2 down, 3 left, 4 right.
#
# What a player has to discover: bright squares are keys you pick up by walking onto them; dark squares are
# doors of the same hue that only the matching key opens; the key you hold is shown bottom right; a door eats
# its key; and picking up a second key throws the first one away. Three levels, each with more doors.
from arcengine import ARCBaseGame, BlockingMode, Camera, GameAction, Level, Sprite

BACKGROUND, WALL, FLOOR, EXIT, PLAYER = 0, 0, 5, 4, 10
PIP_DONE, PIP_NOW, PIP_TODO = 13, 10, 5
KEY_COLOR = {"r": 2, "b": 1, "g": 3}
DOOR_COLOR = {"r": 9, "b": 12, "g": 14}  # the same hue, darker

MAPS = [
    [
        "#########",
        "#.g....P#",
        "#...#...#",
        "#......##",
        "#....G#.#",
        "#..##.E.#",
        "#########",
    ],
    [
        "###########",
        "#b........#",
        "#..G.....P#",
        "#...#...###",
        "#.....g...#",
        "#.#..g...B#",
        "#.......#E#",
        "###########",
    ],
    [
        "#############",
        "#..#.....P..#",
        "#g...#...#..#",
        "####.#...#.##",
        "#E#..G......#",
        "#Rb.##.#....#",
        "#.##...#..#.#",
        "#..g.....Br##",
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


class Keydoor(ARCBaseGame):
    def __init__(self) -> None:
        levels = [
            Level(sprites=[], grid_size=(16, 16), name=f"level {i + 1}", data={"map": rows})
            for i, rows in enumerate(MAPS)
        ]
        super().__init__(
            game_id="keydoor",
            levels=levels,
            camera=Camera(width=16, height=16, background=BACKGROUND, letter_box=BACKGROUND),
            available_actions=[1, 2, 3, 4],
        )

    def on_set_level(self, level: Level) -> None:
        rows = level.get_data("map")
        self._ox, self._oy = (16 - len(rows[0])) // 2, (15 - len(rows)) // 2
        self._walls: set[tuple[int, int]] = set()
        self._keys: dict[tuple[int, int], tuple[str, Sprite]] = {}
        self._doors: dict[tuple[int, int], tuple[str, Sprite]] = {}
        self._exit = (0, 0)
        self._pos = (0, 0)
        self._held: str | None = None
        self._held_sprite: Sprite | None = None
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                px, py = self._ox + x, self._oy + y
                if ch == "#":
                    self._walls.add((x, y))
                    level.add_sprite(_px(WALL, px, py, f"wall{x}_{y}"))
                    continue
                level.add_sprite(_px(FLOOR, px, py, f"floor{x}_{y}"))
                if ch == "E":
                    self._exit = (x, y)
                    level.add_sprite(_px(EXIT, px, py, "exit", layer=1))
                elif ch == "P":
                    self._pos = (x, y)
                elif ch in KEY_COLOR:
                    sprite = _px(KEY_COLOR[ch], px, py, f"key{x}_{y}", layer=1)
                    self._keys[(x, y)] = (ch, sprite)
                    level.add_sprite(sprite)
                elif ch.lower() in DOOR_COLOR and ch.isupper():
                    sprite = _px(DOOR_COLOR[ch.lower()], px, py, f"door{x}_{y}", layer=1)
                    self._doors[(x, y)] = (ch.lower(), sprite)
                    level.add_sprite(sprite)
        self._player = _px(PLAYER, self._ox + self._pos[0], self._oy + self._pos[1], "player", layer=3)
        level.add_sprite(self._player)
        for i in range(len(MAPS)):
            color = PIP_DONE if i < self.level_index else PIP_NOW if i == self.level_index else PIP_TODO
            level.add_sprite(_px(color, 1 + 2 * i, 15, f"pip{i}"))

    def _show_held(self) -> None:
        level = self.current_level
        if self._held_sprite is not None:
            level.remove_sprite(self._held_sprite)
            self._held_sprite = None
        if self._held is not None:
            self._held_sprite = _px(KEY_COLOR[self._held], 14, 15, "held")
            level.add_sprite(self._held_sprite)

    def step(self) -> None:
        delta = MOVES.get(self.action.id)
        if delta is not None:
            target = (self._pos[0] + delta[0], self._pos[1] + delta[1])
            blocked = target in self._walls
            if not blocked and target in self._doors:
                color, sprite = self._doors[target]
                if self._held == color:  # the door opens and takes the key with it
                    self.current_level.remove_sprite(sprite)
                    del self._doors[target]
                    self._held = None
                    self._show_held()
                else:
                    blocked = True
            if not blocked:
                self._pos = target
                self._player.set_position(self._ox + target[0], self._oy + target[1])
                if target in self._keys:  # picking a key up replaces (and loses) whatever you held
                    color, sprite = self._keys.pop(target)
                    self.current_level.remove_sprite(sprite)
                    self._held = color
                    self._show_held()
                if target == self._exit:
                    self.next_level()
        self.complete_action()
