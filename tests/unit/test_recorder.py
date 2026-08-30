import json

from backend.game_sources.base import ActionInputEcho, FrameData, GameState
from backend.recorder import SCHEMA_VERSION, Recorder


def make_frame_data(guid="guid-1", action_id=1, state=GameState.NOT_FINISHED):
    return FrameData(
        source="remote",
        game_id="ls20",
        guid=guid,
        frame=[[[0] * 64 for _ in range(64)]],
        state=state,
        levels_completed=0,
        win_levels=3,
        action_input=ActionInputEcho(id=action_id, data=None, reasoning=None),
        available_actions=[1, 2, 3, 4, 5, 6],
        full_reset=False,
    )


def test_append_writes_one_valid_json_line_per_call(tmp_path):
    recorder = Recorder(tmp_path, "remote", "ls20")

    recorder.append(make_frame_data(action_id=0))
    recorder.append(make_frame_data(action_id=1))
    recorder.append(make_frame_data(action_id=6))

    lines = recorder.path.read_text().strip().splitlines()
    assert len(lines) == 3

    parsed = [json.loads(line) for line in lines]
    assert [p["step_index"] for p in parsed] == [0, 1, 2]
    assert [p["action_id"] for p in parsed] == [0, 1, 6]
    assert all(p["schema_version"] == SCHEMA_VERSION for p in parsed)
    assert all(p["source"] == "remote" and p["game_id"] == "ls20" for p in parsed)


def test_filename_pattern(tmp_path):
    recorder = Recorder(tmp_path, "remote", "ls20")
    assert recorder.path.parent == tmp_path
    assert recorder.path.name.startswith("remote.ls20.")
    assert recorder.path.name.endswith(".recording.jsonl")


def test_step_count_tracks_appends(tmp_path):
    recorder = Recorder(tmp_path, "remote", "ls20")
    assert recorder.step_count == 0
    recorder.append(make_frame_data())
    assert recorder.step_count == 1
