"""ArcadeGameSource against a real (OFFLINE-mode, no network) Arcade and a
tiny fixture game (tests/fixtures/environment_files/tst1) -- this exercises
the real arc_agi/arcengine execution path our normalization depends on,
rather than mocking it away.
"""

from pathlib import Path

import pytest
from arc_agi import Arcade, OperationMode

from backend.game_sources.arcade import ArcadeGameSource, list_games
from backend.game_sources.base import GameSourceError

FIXTURES_DIR = str(Path(__file__).resolve().parent.parent / "fixtures" / "environment_files")


@pytest.fixture
def offline_arcade():
    return Arcade(operation_mode=OperationMode.OFFLINE, environments_dir=FIXTURES_DIR)


def test_list_games_finds_the_fixture(offline_arcade):
    games = list_games(offline_arcade)
    assert [g.game_id for g in games] == ["tst1"]
    assert games[0].source == "local"
    assert games[0].title == "Test Game"


async def test_reset_returns_a_local_frame(offline_arcade):
    source = ArcadeGameSource(offline_arcade, "tst1")
    frame_data = await source.reset()

    assert frame_data.source == "local"
    assert frame_data.game_id == "tst1"
    assert frame_data.guid
    assert len(frame_data.frame) == 1
    assert len(frame_data.frame[0]) == 64  # frames always render to the full 64x64 camera
    assert frame_data.state.value == "NOT_FINISHED"
    assert frame_data.action_input.id == 0


async def test_action1_wins_the_single_level_game(offline_arcade):
    source = ArcadeGameSource(offline_arcade, "tst1")
    await source.reset()

    frame_data = await source.step(1)

    assert frame_data.state.value == "WIN"
    assert frame_data.levels_completed == 1
    assert frame_data.action_input.id == 1


async def test_action6_carries_xy_through(offline_arcade):
    source = ArcadeGameSource(offline_arcade, "tst1")
    await source.reset()

    frame_data = await source.step(6, x=3, y=5)

    assert frame_data.action_input.id == 6
    assert frame_data.action_input.data == {"x": 3, "y": 5}


async def test_reset_action_id_zero_resets(offline_arcade):
    source = ArcadeGameSource(offline_arcade, "tst1")
    await source.reset()
    await source.step(1)  # win

    frame_data = await source.step(0)

    assert frame_data.state.value == "NOT_FINISHED"
    assert frame_data.action_input.id == 0


async def test_step_before_reset_raises():
    source = ArcadeGameSource(Arcade(operation_mode=OperationMode.OFFLINE, environments_dir=FIXTURES_DIR), "tst1")
    with pytest.raises(GameSourceError, match="before reset"):
        await source.step(1)


async def test_unknown_game_id_raises(offline_arcade):
    source = ArcadeGameSource(offline_arcade, "does-not-exist")
    with pytest.raises(GameSourceError, match="could not load"):
        await source.reset()
