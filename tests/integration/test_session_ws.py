"""WebSocket session loop, driven end-to-end against a stub ArcadeGameSource
so no real download or game execution happens. Covers SLICES.md V1's
integration test plan: reset -> N actions -> the recording file has N+1
well-formed JSONL lines.
"""

import json

from fastapi.testclient import TestClient

from backend import server
from backend.game_sources.base import (
    ActionInputEcho,
    FrameData,
    GameMeta,
    GameSourceError,
    GameState,
)


class StubGameSource:
    source = "local"

    def __init__(self, arcade, game_id: str) -> None:
        self.game_id = game_id
        self._guid = "guid-1"

    async def reset(self) -> FrameData:
        return self._frame(action_id=0)

    async def step(self, action_id: int, x=None, y=None) -> FrameData:
        return self._frame(action_id=action_id)

    async def close(self) -> None:
        pass

    def _frame(self, action_id: int) -> FrameData:
        return FrameData(
            source="local",
            game_id=self.game_id,
            guid=self._guid,
            frame=[[[0] * 64 for _ in range(64)]],
            state=GameState.NOT_FINISHED,
            levels_completed=0,
            win_levels=3,
            action_input=ActionInputEcho(id=action_id, data=None, reasoning=None),
            available_actions=[1, 2, 3, 4, 5, 6],
            full_reset=(action_id == 0),
        )


async def stub_make_arcade(api_key):
    return object()  # opaque sentinel; StubGameSource ignores it


def stub_list_games(arcade):
    return [GameMeta(game_id="tst1", source="local", title="Test Game")]


async def stub_close_arcade(arcade):
    pass


def make_client(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "ArcadeGameSource", StubGameSource)
    monkeypatch.setattr(server, "make_arcade", stub_make_arcade)
    monkeypatch.setattr(server, "list_games", stub_list_games)
    monkeypatch.setattr(server, "close_arcade", stub_close_arcade)
    monkeypatch.setattr(server, "api_key_from_env", lambda: "test-key")
    monkeypatch.setattr(server, "recordings_dir_from_env", lambda: tmp_path)
    return TestClient(server.app)


def test_start_then_three_actions_produces_four_recording_lines(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)

    with client.websocket_connect("/ws/session") as ws:
        games_message = ws.receive_json()
        assert games_message["type"] == "games"
        assert games_message["games"][0]["game_id"] == "tst1"

        ws.send_json({"type": "start", "game_id": "tst1"})
        frame_message = ws.receive_json()
        assert frame_message["type"] == "frame"
        assert frame_message["frame_data"]["action_input"]["id"] == 0

        for action_id in (1, 2, 6):
            ws.send_json({"type": "action", "action_id": action_id})
            reply = ws.receive_json()
            assert reply["type"] == "frame"
            assert reply["frame_data"]["action_input"]["id"] == action_id

    recordings = list(tmp_path.glob("*.recording.jsonl"))
    assert len(recordings) == 1
    lines = recordings[0].read_text().strip().splitlines()
    assert len(lines) == 4
    parsed = [json.loads(line) for line in lines]
    assert [p["step_index"] for p in parsed] == [0, 1, 2, 3]
    assert [p["action_id"] for p in parsed] == [0, 1, 2, 6]


def test_action_before_start_returns_error_not_disconnect(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)

    with client.websocket_connect("/ws/session") as ws:
        ws.receive_json()  # games
        ws.send_json({"type": "action", "action_id": 1})
        reply = ws.receive_json()
        assert reply["type"] == "error"
        assert "start" in reply["message"]

        # connection still alive after an error
        ws.send_json({"type": "start", "game_id": "tst1"})
        frame_message = ws.receive_json()
        assert frame_message["type"] == "frame"


def test_game_source_error_during_action_is_surfaced_not_raised(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)

    class FailingStep(StubGameSource):
        async def step(self, action_id: int, x=None, y=None) -> FrameData:
            raise GameSourceError("simulated failure")

    monkeypatch.setattr(server, "ArcadeGameSource", FailingStep)

    with client.websocket_connect("/ws/session") as ws:
        ws.receive_json()  # games
        ws.send_json({"type": "start", "game_id": "tst1"})
        ws.receive_json()  # frame from reset
        ws.send_json({"type": "action", "action_id": 1})
        reply = ws.receive_json()
        assert reply["type"] == "error"
        assert "simulated failure" in reply["message"]
