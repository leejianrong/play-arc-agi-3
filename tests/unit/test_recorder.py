import json

from backend.game_sources.base import ActionInputEcho, FrameData, GameState
from backend.recorder import SCHEMA_VERSION, Recorder


def make_frame_data(guid="guid-1", action_id=1, state=GameState.NOT_FINISHED):
    return FrameData(
        source="local",
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
    recorder = Recorder(tmp_path, "local", "ls20", "full")

    recorder.append(make_frame_data(action_id=0))
    recorder.append(make_frame_data(action_id=1))
    recorder.append(make_frame_data(action_id=6))

    lines = recorder.path.read_text().strip().splitlines()
    assert len(lines) == 3

    parsed = [json.loads(line) for line in lines]
    assert [p["step_index"] for p in parsed] == [0, 1, 2]
    assert [p["action_id"] for p in parsed] == [0, 1, 6]
    assert all(p["schema_version"] == SCHEMA_VERSION for p in parsed)
    assert all(p["source"] == "local" and p["game_id"] == "ls20" for p in parsed)


def test_full_mode_includes_the_frame(tmp_path):
    recorder = Recorder(tmp_path, "local", "ls20", "full")
    recorder.append(make_frame_data())

    line = json.loads(recorder.path.read_text().strip())
    assert line["mode"] == "full"
    assert line["frame"] is not None
    assert len(line["frame"]) == 1


def test_lean_mode_omits_the_frame(tmp_path):
    recorder = Recorder(tmp_path, "local", "ls20", "lean")
    recorder.append(make_frame_data())

    line = json.loads(recorder.path.read_text().strip())
    assert line["mode"] == "lean"
    assert line["frame"] is None
    # everything else that isn't the (large) frame grid is still present
    assert line["state"] == "NOT_FINISHED"
    assert line["levels_completed"] == 0
    assert line["available_actions"] == [1, 2, 3, 4, 5, 6]


def test_filename_pattern_includes_mode(tmp_path):
    recorder = Recorder(tmp_path, "local", "ls20", "lean")
    assert recorder.path.parent == tmp_path
    assert recorder.path.name.startswith("local.ls20.lean.")
    assert recorder.path.name.endswith(".recording.jsonl")


def test_step_count_tracks_appends(tmp_path):
    recorder = Recorder(tmp_path, "local", "ls20", "full")
    assert recorder.step_count == 0
    recorder.append(make_frame_data())
    assert recorder.step_count == 1
