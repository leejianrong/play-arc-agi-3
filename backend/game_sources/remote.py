"""Thin client for the real ARC-AGI-3 competition games (ADR-0002).

Contract confirmed by reading arcprize/ARC-AGI's own client source
(arc_agi/remote_wrapper.py, arc_agi/api.py) rather than the hosted docs,
which proved incomplete on the scorecard requirement:

    POST /api/scorecard/open  {tags}              -> {card_id}
    POST /api/cmd/RESET       {card_id, game_id}  -> FrameData (first reset)
    POST /api/cmd/RESET       {game_id, guid}     -> FrameData (later resets)
    POST /api/cmd/ACTION{1-7} {game_id, guid, x?, y?} -> FrameData
    POST /api/scorecard/close {card_id}

x/y (ACTION6 only) are top-level payload fields, not nested under "data".
"""

from __future__ import annotations

import os
from typing import Optional

import httpx

from .base import ActionId, ActionInputEcho, FrameData, GameMeta, GameSource, GameSourceError, GameState

DEFAULT_BASE_URL = "https://three.arcprize.org"


def _parse_frame_data(payload: dict) -> FrameData:
    try:
        action_input = payload["action_input"] or {}
        return FrameData(
            source="remote",
            game_id=payload["game_id"],
            guid=payload["guid"],
            frame=payload["frame"],
            state=GameState(payload["state"]),
            levels_completed=payload["levels_completed"],
            win_levels=payload["win_levels"],
            action_input=ActionInputEcho(
                id=action_input.get("id", 0),
                data=action_input.get("data"),
                reasoning=action_input.get("reasoning"),
            ),
            available_actions=payload.get("available_actions", []),
            full_reset=payload.get("full_reset", False),
        )
    except (KeyError, ValueError) as exc:
        raise GameSourceError(f"malformed FrameData from remote API: {exc}") from exc


async def list_remote_games(api_key: str, base_url: str = DEFAULT_BASE_URL) -> list[GameMeta]:
    async with httpx.AsyncClient(base_url=base_url, headers={"X-API-Key": api_key}, timeout=10) as client:
        try:
            response = await client.get("/api/games")
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GameSourceError(f"failed to list remote games: {exc}") from exc
        return [
            GameMeta(game_id=g["game_id"], source="remote", title=g.get("title"), tags=g.get("tags"))
            for g in response.json()
        ]


class RemoteGameSource:
    """A play session for one real ARC-AGI-3 game.

    Opens its own scorecard on construction and closes it on close() — the
    card_id never leaves this class; GameSource callers only see game_id/guid.
    """

    source = "remote"

    def __init__(self, game_id: str, api_key: str, base_url: str = DEFAULT_BASE_URL) -> None:
        self.game_id = game_id
        self._client = httpx.AsyncClient(base_url=base_url, headers={"X-API-Key": api_key}, timeout=10)
        self._card_id: Optional[str] = None
        self._guid: Optional[str] = None

    async def _open_scorecard(self) -> str:
        try:
            response = await self._client.post("/api/scorecard/open", json={"tags": ["human"]})
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GameSourceError(f"failed to open scorecard: {exc}") from exc
        return response.json()["card_id"]

    async def reset(self) -> FrameData:
        if self._card_id is None:
            self._card_id = await self._open_scorecard()

        payload: dict = {"game_id": self.game_id}
        if self._guid:
            payload["guid"] = self._guid
        else:
            payload["card_id"] = self._card_id

        try:
            response = await self._client.post("/api/cmd/RESET", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GameSourceError(f"RESET failed for {self.game_id}: {exc}") from exc

        frame_data = _parse_frame_data(response.json())
        self._guid = frame_data.guid
        return frame_data

    async def step(self, action_id: int, x: Optional[int] = None, y: Optional[int] = None) -> FrameData:
        if self._guid is None:
            raise GameSourceError("cannot step before reset()")
        if action_id == ActionId.RESET:
            return await self.reset()

        payload: dict = {"game_id": self.game_id, "guid": self._guid}
        if x is not None:
            payload["x"] = x
        if y is not None:
            payload["y"] = y

        try:
            response = await self._client.post(f"/api/cmd/ACTION{int(action_id)}", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GameSourceError(f"ACTION{int(action_id)} failed for {self.game_id}: {exc}") from exc

        return _parse_frame_data(response.json())

    async def close(self) -> None:
        try:
            if self._card_id is not None:
                await self._client.post("/api/scorecard/close", json={"card_id": self._card_id})
        finally:
            await self._client.aclose()


def api_key_from_env() -> str:
    key = os.environ.get("ARC_API_KEY")
    if not key:
        raise GameSourceError(
            "ARC_API_KEY is not set. Get a key from https://arcprize.org/platform and set it in .env."
        )
    return key
