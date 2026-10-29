"""The custom games (ARC-92): every level is winnable and not trivial, the hidden rules behave as designed,
and the games play through the same engine path the app uses.

Solvability is checked by replaying an independent solver's answer through the real engine. The slow generic
engine search (every level, every game) runs with RUN_SLOW_TESTS=1.
"""

import json
import os
from pathlib import Path

import pytest
from arc_agi import Arcade, OperationMode

from backend.annotations.policy import load_policy
from backend.game_sources.arcade import list_games
from tests.helpers import reference_solvers as ref
from tests.helpers.solver import (
    CUSTOM_DIR,
    apply,
    crates_solution,
    dpad,
    lights_out_presses,
    load_game_class,
    solve,
)

GAMES = ["crates", "keydoor", "lamps", "slide", "twins"]
# Fewest moves (clicks for lamps) per level: guards against levels drifting trivial or unsolvable.
MIN_MOVES = {
    "slide": [4, 7, 11],
    "lamps": [3, 5, 7],
    "keydoor": [13, 22, 45],
    "twins": [7, 15, 20],
    "crates": [14, 27, 40],
}
LAMP_CELL = {3: 3, 4: 3, 5: 2}


def fresh(game_id, level=0, rows=None):
    """A game at `level`, built the way the engine builds it (a clean clone, set once).

    `rows` swaps in a tiny hand-made map to test one rule in isolation. (Calling set_level twice on the
    same level object would stack duplicate sprites; the engine itself never does, a reset re-clones.)
    """
    game = load_game_class(game_id)()
    if rows is not None:
        game._clean_levels[level]._data["map"] = rows
        game._levels[level] = game._clean_levels[level].clone()
    if rows is not None or level != 0:
        game.set_level(level)
    return game


def dpad_moves(game, actions):
    frame = None
    for action in actions:
        frame = apply(game, (action, None, None))
    return frame


def level_map(game_id, level):
    return fresh(game_id, level).current_level.get_data("map")


def lamp_click(game, cell):
    """Display coordinates (0-63) of the middle of lamp `cell` on the current board."""
    n, size = game._n, game._size
    cx, cy = cell % n, cell // n
    gx, gy = game._ox + cx * game._pitch + size // 2, game._oy + cy * game._pitch + size // 2
    return 6, gx * 4 + 2, gy * 4 + 2  # the 16x16 camera is scaled 4x


def solution_for(game_id, level):
    if game_id == "slide":
        return ref.slide(level_map(game_id, level))
    if game_id == "keydoor":
        return ref.keydoor(level_map(game_id, level))
    if game_id == "twins":
        return ref.twins(level_map(game_id, level))
    if game_id == "crates":
        return crates_solution(level_map(game_id, level))
    raise AssertionError(game_id)


# -- the folder, its metadata, and how the app sees it ---------------------------------------------


def test_every_game_folder_has_matching_metadata_and_a_custom_tag():
    found = sorted(p.name for p in CUSTOM_DIR.iterdir() if p.is_dir())
    assert found == GAMES
    for game_id in GAMES:
        meta = json.loads((CUSTOM_DIR / game_id / "metadata.json").read_text())
        assert meta["game_id"] == game_id and meta["title"] and "custom" in meta["tags"]
        assert meta["class_name"] == game_id.capitalize()  # ids are not 4 characters; the loader needs this
        assert (CUSTOM_DIR / game_id / f"{game_id}.py").is_file()


def test_the_real_arcade_lists_them_with_titles_and_tags():
    arcade = Arcade(operation_mode=OperationMode.OFFLINE, environments_dir=str(CUSTOM_DIR))
    games = {g.game_id: g for g in list_games(arcade)}
    assert sorted(games) == GAMES
    assert all(g.title and "custom" in g.tags for g in games.values())


@pytest.mark.parametrize("game_id", GAMES)
async def test_the_toolkit_loader_runs_each_game_the_way_the_app_does(game_id):
    """Through arc_agi's own loader (`Arcade.make`) and our ArcadeGameSource, not by importing the class.
    This catches loader conventions: the toolkit derives a game's file and class name from its id's first
    four characters unless metadata.json sets `class_name`."""
    from backend.game_sources.arcade import ArcadeGameSource

    arcade = Arcade(operation_mode=OperationMode.OFFLINE, environments_dir=str(CUSTOM_DIR))
    source = ArcadeGameSource(arcade, game_id)
    first = await source.reset()
    assert first.game_id == game_id and first.state.value == "NOT_FINISHED" and first.win_levels == 3
    moved = await source.step(6, x=30, y=30) if game_id == "lamps" else await source.step(1)
    assert moved.frame and moved.available_actions == first.available_actions


def test_policy_classifies_them_as_trainable():
    policy = load_policy(Path(CUSTOM_DIR).parent / "data_policy.json")
    assert {g: policy.classify(g) for g in GAMES} == dict.fromkeys(GAMES, "train-ok")


@pytest.mark.parametrize("game_id", GAMES)
def test_three_levels_a_full_size_frame_and_the_expected_actions(game_id):
    game = fresh(game_id)
    frame = game.perform_action(
        __import__("arcengine").ActionInput(id=__import__("arcengine").GameAction.RESET)
    )
    assert len(frame.frame[-1]) == 64 and len(frame.frame[-1][0]) == 64
    assert frame.win_levels == 3 and frame.levels_completed == 0
    expected = [6] if game_id == "lamps" else [1, 2, 3, 4]
    assert frame.available_actions == expected


# -- every level is winnable, and takes real work ---------------------------------------------------


@pytest.mark.parametrize("game_id", ["slide", "keydoor", "twins", "crates"])
@pytest.mark.parametrize("level", [0, 1, 2])
def test_replaying_the_reference_solution_clears_the_level_in_the_engine(game_id, level):
    solution = solution_for(game_id, level)
    assert solution is not None, "no solution: the level is unwinnable"
    assert len(solution) == MIN_MOVES[game_id][level]
    game = fresh(game_id, level)
    frame = dpad_moves(game, solution[:-1])
    assert frame is None or frame.levels_completed == 0  # not won a move early
    frame = apply(game, (solution[-1], None, None))
    assert frame.levels_completed == 1 or frame.state.value == "WIN"


@pytest.mark.parametrize("level", [0, 1, 2])
def test_lamps_boards_are_solvable_and_the_algebraic_solution_clears_them_in_the_engine(level):
    game = fresh("lamps", level)
    presses = lights_out_presses(game._n, game._lit)
    assert len(presses) == MIN_MOVES["lamps"][level]
    frame = None
    for cell in presses:
        frame = apply(game, lamp_click(game, cell))
    assert frame.levels_completed == 1 or frame.state.value == "WIN"


def test_the_last_level_of_each_game_ends_in_a_win():
    for game_id in ["slide", "keydoor", "twins", "crates"]:
        game = fresh(game_id, 2)
        frame = dpad_moves(game, solution_for(game_id, 2))
        assert (
            frame.state.value == "WIN" and frame.levels_completed == 1 + 0 * 1
        )  # set_level(2) starts at score 0


@pytest.mark.skipif(not os.environ.get("RUN_SLOW_TESTS"), reason="slow: set RUN_SLOW_TESTS=1")
@pytest.mark.parametrize("game_id", ["slide", "keydoor", "twins"])
def test_generic_engine_search_agrees_with_the_reference_lengths(game_id):
    cls = load_game_class(game_id)
    for level, expected in enumerate(MIN_MOVES[game_id]):
        found = solve(cls, level, dpad)
        assert found is not None and len(found) == expected


def test_play_is_deterministic_and_reset_restarts_the_level():
    game = fresh("slide", 1)
    first = [apply(game, (a, None, None)).frame[-1] for a in (3, 1, 4)]
    again = fresh("slide", 1)
    assert [apply(again, (a, None, None)).frame[-1] for a in (3, 1, 4)] == first
    after_reset = apply(game, (0, None, None)).frame[-1]
    assert (
        after_reset == fresh("slide", 1).camera.render(fresh("slide", 1).current_level.get_sprites()).tolist()
    )


# -- the hidden rules, on tiny hand-made maps ------------------------------------------------------


def test_slide_runs_until_a_wall_and_the_goal_catches_you_mid_slide():
    game = fresh("slide", 0, ["#######", "#P...G#", "#.....#", "#######"])
    apply(game, (2, None, None))  # down: one square of travel to the wall
    assert game._pos == (1, 2)
    apply(game, (1, None, None))  # back up
    assert game._pos == (1, 1)
    frame = apply(game, (4, None, None))  # right: passes nothing, falls into the goal at x=5
    assert frame.levels_completed == 1


def test_slide_a_blocked_move_does_nothing():
    game = fresh("slide", 0, ["####", "#PG#", "####"])
    before = game._pos
    apply(game, (3, None, None))
    assert game._pos == before


def test_keydoor_matching_key_opens_the_door_and_is_used_up():
    game = fresh("keydoor", 0, ["########", "#PrR.E.#", "########"])
    apply(game, (4, None, None))
    assert game._held == "r"
    apply(game, (4, None, None))  # into the red door
    assert game._pos == (3, 1) and game._held is None and not game._doors
    assert apply(game, (4, None, None)).levels_completed == 0
    assert apply(game, (4, None, None)).levels_completed == 1


def test_keydoor_wrong_key_does_not_open_and_a_door_blocks_without_one():
    game = fresh("keydoor", 0, ["#########", "#PbRE...#", "#########"])
    apply(game, (4, None, None))
    assert game._held == "b"
    apply(game, (4, None, None))  # a red door, but you hold blue
    assert game._pos == (2, 1) and game._doors
    bare = fresh("keydoor", 0, ["#######", "#PRE..#", "#######"])
    apply(bare, (4, None, None))
    assert bare._pos == (1, 1)


def test_keydoor_picking_up_a_second_key_loses_the_first():
    game = fresh("keydoor", 0, ["########", "#PrbRE.#", "########"])
    apply(game, (4, None, None))
    apply(game, (4, None, None))
    assert game._held == "b"  # the red key is gone
    apply(game, (4, None, None))  # a red door: blocked
    assert game._pos == (3, 1)


def test_twins_move_together_mirror_sideways_and_one_can_be_blocked():
    pairs = [("#######", "#######"), ("#P...T#", "#T...P#"), ("#######", "#######")]
    game = fresh("twins", 0, pairs)
    assert game._pos == [(1, 1), (5, 1)]
    apply(game, (4, None, None))  # right: the left twin goes right, the right twin goes LEFT
    assert game._pos == [(2, 1), (4, 1)]
    apply(game, (4, None, None))
    apply(game, (4, None, None))
    assert game._pos == [(4, 1), (2, 1)]
    assert apply(game, (4, None, None)).levels_completed == 1  # both on their targets at once


def test_twins_a_wall_stops_one_twin_while_the_other_still_moves():
    pairs = [("#####", "#####"), ("#P.T#", "#TP.#"), ("#####", "#####")]
    game = fresh("twins", 0, pairs)
    apply(game, (3, None, None))  # left: left twin hits the wall, right twin moves right
    assert game._pos == [(1, 1), (3, 1)]


def test_crates_push_one_square_and_cannot_push_into_walls_or_other_crates():
    game = fresh("crates", 0, ["#######", "#PCC.T#", "#######"])
    apply(game, (4, None, None))  # two crates in a row: blocked
    assert game._pos == (1, 1) and game._crates == {(2, 1), (3, 1)}
    stuck = fresh("crates", 0, ["######", "#PC#T#", "######"])
    apply(stuck, (4, None, None))  # a wall behind the crate: nothing moves
    assert stuck._pos == (1, 1) and stuck._crates == {(2, 1)}
    single = fresh("crates", 0, ["######", "#PC.T#", "######"])
    apply(single, (4, None, None))  # a free square behind: the crate moves one square and you follow
    assert single._pos == (2, 1) and single._crates == {(3, 1)}


def test_crates_covering_every_target_clears_the_level():
    game = fresh("crates", 0, ["#####", "#PCT#", "#####"])
    assert apply(game, (4, None, None)).levels_completed == 1


def test_crates_on_a_target_are_drawn_in_the_home_colour():
    # Two targets for one crate, so the push does not clear the level (which would load the next one).
    game = fresh("crates", 0, ["#######", "#PCT.T#", "#######"])

    def colours():
        return {int(s.pixels[0][0]) for s in game.current_level.get_sprites() if s.name.startswith("crate")}

    assert colours() == {7}
    apply(game, (4, None, None))
    assert colours() == {3}


def test_lamps_a_click_flips_the_lamp_and_its_neighbours_only_and_gaps_do_nothing():
    game = fresh("lamps", 0)
    before = list(game._lit)
    game.perform_action(
        __import__("arcengine").ActionInput(
            id=__import__("arcengine").GameAction.ACTION6, data={"x": 0, "y": 0}
        )
    )
    assert game._lit == before  # outside the board
    apply(game, lamp_click(game, 4))  # the middle lamp flips itself and its four neighbours
    flipped = [i for i in range(9) if game._lit[i] != before[i]]
    assert flipped == [1, 3, 4, 5, 7]
    gap = (6, (game._ox + 3) * 4 + 2, (game._oy + 1) * 4 + 2)  # the 1px gap between two lamps
    after = list(game._lit)
    apply(game, gap)
    assert game._lit == after
