"""Replay verification against a real (OFFLINE, no network) fixture game: record a session through the real
Recorder, then check that verify_replay accepts it and pinpoints a tampered step."""

import asyncio
import json
from pathlib import Path

import pytest
from arc_agi import Arcade, OperationMode

from backend.game_sources.arcade import ArcadeGameSource
from backend.recorder import Recorder
from backend.timeline import load_jsonl, main, verify_replay

FIXTURES = str(Path(__file__).resolve().parent.parent / "fixtures" / "environment_files")


@pytest.fixture
def arcade():
    return Arcade(operation_mode=OperationMode.OFFLINE, environments_dir=FIXTURES)


async def record_session(arcade, tmp_path, mode="lean", actions=((6, 3, 4), (2, None, None))):
    source = ArcadeGameSource(arcade, "tst1")
    recorder = Recorder(tmp_path, "local", "tst1", mode)
    recorder.append(await source.reset())
    for action, x, y in actions:
        recorder.append(await source.step(action, x=x, y=y))
    return recorder.path


async def test_a_recorded_session_replays_identically_by_frame_hash(arcade, tmp_path):
    path = await record_session(arcade, tmp_path)
    steps, _ = load_jsonl(path)
    result = await verify_replay(steps, arcade)
    assert result.ok and result.checked == 3 and result.hashed == 3 and result.note == ""


async def test_changing_a_recorded_action_fails_at_that_step(arcade, tmp_path):
    path = await record_session(arcade, tmp_path)
    steps, _ = load_jsonl(path)
    steps[2]["action_id"] = 1  # the recording says ACTION2 (lose); replay will WIN instead
    result = await verify_replay(steps, arcade)
    assert not result.ok
    d = result.divergence
    assert d.step_index == 2 and d.what == "state" and (d.recorded, d.replayed) == ("GAME_OVER", "WIN")


async def test_a_tampered_frame_hash_is_caught_even_when_state_matches(arcade, tmp_path):
    path = await record_session(arcade, tmp_path)
    steps, _ = load_jsonl(path)
    steps[1]["frame_sha256"] = "0" * 64
    result = await verify_replay(steps, arcade)
    assert result.divergence.step_index == 1 and result.divergence.what == "frame_sha256"


async def test_old_recordings_without_hashes_fall_back_to_state_and_levels(arcade, tmp_path):
    path = await record_session(arcade, tmp_path)
    steps, _ = load_jsonl(path)
    for s in steps:
        del s["frame_sha256"]  # what a schema-2 lean recording looks like
    result = await verify_replay(steps, arcade)
    assert result.ok and result.hashed == 0 and "no frame hashes" in result.note
    steps[2]["levels_completed"] = 5
    assert (await verify_replay(steps, arcade)).divergence.what == "levels_completed"


async def test_full_recordings_without_hashes_are_checked_by_their_stored_frames(arcade, tmp_path):
    path = await record_session(arcade, tmp_path, mode="full")
    steps, _ = load_jsonl(path)
    for s in steps:
        del s["frame_sha256"]
    result = await verify_replay(steps, arcade)
    assert result.ok and result.hashed == 3
    steps[1]["frame"][0][0][0] = 9
    assert (await verify_replay(steps, arcade)).divergence.what == "frame_sha256"


def test_cli_renders_and_verifies_and_signals_failure_with_its_exit_code(arcade, tmp_path, capsys):
    # Sync on purpose: the CLI starts its own event loop, which can't nest inside an async test.
    path = asyncio.run(record_session(arcade, tmp_path))
    assert main([str(path), "--verify", "--env-dir", FIXTURES]) == 0
    out = capsys.readouterr()
    assert "# Timeline:" in out.out and "VERIFY OK" in out.err

    rows, _ = load_jsonl(path)
    rows[2]["action_id"] = 1
    path.write_text("\n".join(json.dumps(r) for r in rows))
    assert main([str(path), "--verify", "--env-dir", FIXTURES]) == 1
    assert "VERIFY FAILED at step 2 (state)" in capsys.readouterr().err
    assert main([str(tmp_path / "missing.recording.jsonl")]) == 2
