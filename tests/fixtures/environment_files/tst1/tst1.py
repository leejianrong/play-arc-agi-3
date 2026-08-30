# Minimal ARCBaseGame fixture for testing ArcadeGameSource against a real
# (OFFLINE-mode, no network) arc_agi/arcengine execution path, modeled on
# arcprize/ARC-AGI's own test_environment_files/game1/bt11.py.
#
# ACTION1 wins immediately (single level). ACTION2 loses. ACTION6 (click)
# is accepted but does nothing, to exercise the x/y action path.
from arcengine import ARCBaseGame, Camera, GameAction, Level

BACKGROUND_COLOR = 0


class Tst1(ARCBaseGame):
    def __init__(self) -> None:
        camera = Camera(background=BACKGROUND_COLOR, letter_box=BACKGROUND_COLOR)
        levels = [Level(sprites=[], grid_size=(8, 8))]
        super().__init__(
            game_id="tst1",
            levels=levels,
            camera=camera,
            available_actions=[1, 2, 6],
        )

    def step(self) -> None:
        if self.action.id == GameAction.ACTION1:
            self.next_level()
        elif self.action.id == GameAction.ACTION2:
            self.lose()
        self.complete_action()
