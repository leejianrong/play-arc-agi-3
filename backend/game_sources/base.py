"""The GameSource contract (ADR-0002): one normalized FrameData shape,
produced by either a RemoteGameSource or a LocalGameSource, so nothing
downstream (WebSocket session handling, rendering, recording) needs to know
which one is active.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Literal, Optional, Protocol


class GameState(StrEnum):
    NOT_PLAYED = "NOT_PLAYED"
    NOT_FINISHED = "NOT_FINISHED"
    WIN = "WIN"
    GAME_OVER = "GAME_OVER"


class ActionId(IntEnum):
    RESET = 0
    ACTION1 = 1
    ACTION2 = 2
    ACTION3 = 3
    ACTION4 = 4
    ACTION5 = 5
    ACTION6 = 6
    ACTION7 = 7


GameSourceKind = Literal["remote", "local"]


@dataclass(frozen=True, slots=True)
class ActionInputEcho:
    """Echo of the action that produced a FrameData, as the API returns it."""

    id: int
    data: Optional[dict] = None
    reasoning: Optional[dict] = None


@dataclass(frozen=True, slots=True)
class FrameData:
    source: GameSourceKind
    game_id: str
    guid: str
    frame: list
    state: GameState
    levels_completed: int
    win_levels: int
    action_input: ActionInputEcho
    available_actions: list[int]
    full_reset: bool = False

    def to_wire(self) -> dict:
        return {
            "source": self.source,
            "game_id": self.game_id,
            "guid": self.guid,
            "frame": self.frame,
            "state": str(self.state),
            "levels_completed": self.levels_completed,
            "win_levels": self.win_levels,
            "action_input": {
                "id": self.action_input.id,
                "data": self.action_input.data,
                "reasoning": self.action_input.reasoning,
            },
            "available_actions": self.available_actions,
            "full_reset": self.full_reset,
        }


@dataclass(frozen=True, slots=True)
class GameMeta:
    game_id: str
    source: GameSourceKind
    title: Optional[str] = None
    tags: Optional[list[str]] = None


class GameSource(Protocol):
    """A play session bound to one game. Construct one per session."""

    game_id: str
    source: GameSourceKind

    async def reset(self) -> FrameData: ...

    async def step(
        self, action_id: int, x: Optional[int] = None, y: Optional[int] = None
    ) -> FrameData: ...

    async def close(self) -> None: ...


class GameSourceError(Exception):
    """Raised for any GameSource failure the WebSocket layer should surface
    to the UI as an error banner rather than crash the connection."""
