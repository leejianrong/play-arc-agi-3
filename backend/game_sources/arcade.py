"""Local execution of ARC-AGI-3 games via ARC's own arc_agi toolkit (ADR-0004).

Confirmed by reading arc_agi/base.py: OperationMode.NORMAL (the package's own
default) downloads a real game's Python source once via
GET /api/games/{game_id}-{version}/source, then every reset()/step() call
executes that source locally, in-process -- no per-action network round trip.
This replaced the earlier hand-rolled RemoteGameSource (ADR-0002), which hit
the remote API on every single action and was the actual cause of "laggy and
unresponsive" play.

OperationMode.OFFLINE runs the same local-execution path against
hand-authored custom environments (slice V2) with no network at all. Both
modes produce a source="local" FrameData -- what matters to the rest of the
app is that execution is local either way, not which mode got it there.
"""

from __future__ import annotations

import asyncio
import os

from arc_agi import Arcade, OperationMode
from arcengine import FrameDataRaw, GameAction

from .base import (
    ActionId,
    ActionInputEcho,
    FrameData,
    GameMeta,
    GameSourceError,
    GameState,
)

# GameAction's own value-lookup is keyed by (int, action-class) pairs
# internally, so GameAction(1) raises "1 is not a valid GameAction" even
# though GameAction.ACTION1.value == 1. Build a plain int -> member table
# instead of relying on GameAction's constructor.
_ACTIONS_BY_VALUE = {member.value: member for member in GameAction}


def _normalize(
    frame_data_raw: FrameDataRaw | None, game_id: str, fallback_frame: list | None = None
) -> FrameData:
    if frame_data_raw is None:
        raise GameSourceError(
            f"{game_id} produced no frame data (see the server log for the underlying error)"
        )
    # arcengine's own perform_action() deliberately returns frame=[] for any
    # non-RESET action once a game is already WIN/GAME_OVER (confirmed in
    # arcengine/base_game.py) -- "nothing new to render", not a failure. Fall
    # back to the last real frame so FrameData.frame is never empty: the
    # recorder and the frontend both assume a real grid is always present.
    if frame_data_raw.is_empty():
        if fallback_frame is None:
            raise GameSourceError(
                f"{game_id} ended with no frame ever rendered -- press R to restart"
            )
        frame = fallback_frame
    else:
        frame = [layer.tolist() for layer in frame_data_raw.frame]

    action_input = frame_data_raw.action_input
    return FrameData(
        source="local",
        game_id=frame_data_raw.game_id,
        guid=frame_data_raw.guid or "",
        frame=frame,
        state=GameState(frame_data_raw.state.value),
        levels_completed=frame_data_raw.levels_completed,
        win_levels=frame_data_raw.win_levels,
        action_input=ActionInputEcho(
            id=action_input.id.value,
            data=action_input.data or None,
            reasoning=action_input.reasoning,
        ),
        available_actions=frame_data_raw.available_actions,
        full_reset=frame_data_raw.full_reset,
    )


async def make_arcade(api_key: str, environments_dir: str | None = None) -> Arcade:
    """Construct an Arcade for one WebSocket connection, off the event loop
    -- construction fetches the games catalog, a network call."""
    return await asyncio.to_thread(
        Arcade,
        arc_api_key=api_key,
        operation_mode=OperationMode.NORMAL,
        environments_dir=environments_dir or os.environ.get("ARC_ENVIRONMENTS_DIR", "environment_files"),
    )


def list_games(arcade: Arcade) -> list[GameMeta]:
    return [
        GameMeta(game_id=env.game_id, source="local", title=env.title, tags=env.tags)
        for env in arcade.available_environments
    ]


async def close_arcade(arcade: Arcade) -> None:
    await asyncio.to_thread(arcade.close_scorecard)


class ArcadeGameSource:
    """A play session for one game, executed locally via arc_agi.Arcade.

    The Arcade instance (and its scorecard) is owned by the caller -- one per
    WebSocket connection, via make_arcade()/close_arcade() -- so switching
    games mid-session doesn't re-fetch the catalog or open a new scorecard.
    close() here is deliberately a no-op to satisfy the GameSource protocol;
    the caller closes the Arcade's scorecard once, at connection end.
    """

    source = "local"

    def __init__(self, arcade: Arcade, game_id: str, seed: int = 0) -> None:
        self._arcade = arcade
        self.game_id = game_id
        self._seed = seed
        self._env = None
        self._last_frame: list | None = None

    async def reset(self) -> FrameData:
        try:
            self._env = await asyncio.to_thread(self._arcade.make, self.game_id, self._seed)
        except Exception as exc:
            raise GameSourceError(f"failed to load {self.game_id}: {exc}") from exc
        if self._env is None:
            raise GameSourceError(
                f"could not load game {self.game_id!r} -- check it exists and your API key can access it"
            )
        self._last_frame = None
        frame_data = _normalize(self._env.observation_space, self.game_id)
        self._last_frame = frame_data.frame
        return frame_data

    async def step(self, action_id: int, x: int | None = None, y: int | None = None) -> FrameData:
        if self._env is None:
            raise GameSourceError("cannot step before reset()")
        if action_id == ActionId.RESET:
            return await self.reset()

        try:
            action = _ACTIONS_BY_VALUE[action_id]
        except KeyError:
            raise GameSourceError(f"unknown action id {action_id!r}") from None

        data: dict = {}
        if x is not None:
            data["x"] = x
        if y is not None:
            data["y"] = y

        frame_data_raw = await asyncio.to_thread(self._env.step, action, data)
        frame_data = _normalize(frame_data_raw, self.game_id, fallback_frame=self._last_frame)
        self._last_frame = frame_data.frame
        return frame_data

    async def close(self) -> None:
        pass
