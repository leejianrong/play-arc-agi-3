"""Typed notes, phases, mute, end-session and the data-use policy over the websockets (SLICES V4)."""

import json

from backend import server
from backend.game_sources.base import ActionInputEcho, FrameData, GameMeta, GameState
from backend.stt.base import FakeTranscriber
from tests.helpers.audio import silence, speechlike
from tests.integration.test_audio_ws import (
    PCM,
    drain_until,
    install_transcriber,
    sidecar,
    start_annotated,
)
from tests.integration.test_session_ws import StubGameSource, make_client


class LevelStub(StubGameSource):
    """Action 5 clears a level (levels_completed + 1), anything else just moves."""

    levels = 0

    def _frame(self, action_id: int) -> FrameData:
        if action_id == 5:
            LevelStub.levels += 1
        return FrameData(
            source="local", game_id=self.game_id, guid="g", frame=[[[0] * 64 for _ in range(64)]],
            state=GameState.NOT_FINISHED, levels_completed=LevelStub.levels, win_levels=3,
            action_input=ActionInputEcho(id=action_id), available_actions=[1, 2, 3, 4, 5, 6],
        )


def client_for(monkeypatch, tmp_path, stub=StubGameSource):
    LevelStub.levels = 0
    client = make_client(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "ArcadeGameSource", stub)
    install_transcriber(monkeypatch, FakeTranscriber(["spoken thought"]))
    return client


def kinds(tmp_path, kind=None):
    evs = sidecar(tmp_path)
    return [e for e in evs if e["kind"] == kind] if kind else evs


def test_typed_note_is_stored_with_phase_step_and_source(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    with client.websocket_connect("/ws/session") as ws:
        start_annotated(ws)
        ws.send_json({"type": "note", "text": "  the blue block is the player  "})
        saved = ws.receive_json()
        assert saved["type"] == "note_saved" and saved["phase"] == "observe"
        ws.send_json({"type": "note", "text": "   "})  # blank notes are ignored, not stored
    (note,) = kinds(tmp_path, "text")
    assert note["text"] == "the blue block is the player"
    assert (note["source"], note["phase"], note["step_at_end"]) == ("typed", "observe", 0)


def test_first_action_switches_to_probe_and_tells_the_client(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    with client.websocket_connect("/ws/session") as ws:
        start_annotated(ws)
        ws.send_json({"type": "action", "action_id": 1})
        assert ws.receive_json()["type"] == "frame"
        phase = ws.receive_json()
        assert (phase["type"], phase["phase"], phase["reason"]) == ("phase", "probe", "auto_first_action")
        ws.send_json({"type": "action", "action_id": 2})
        assert ws.receive_json()["type"] == "frame"  # no second phase message
        ws.send_json({"type": "phase", "phase": "plan"})
        assert ws.receive_json()["phase"] == "plan"
        ws.send_json({"type": "note", "text": "plan: go up twice"})
        assert ws.receive_json()["phase"] == "plan"
    changes = [(e["phase"], e["reason"]) for e in kinds(tmp_path, "phase_change")]
    assert changes == [("observe", "session_start"), ("probe", "auto_first_action"), ("plan", "manual")]


def test_clearing_a_level_returns_to_observe(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path, LevelStub)
    with client.websocket_connect("/ws/session") as ws:
        start_annotated(ws)
        ws.send_json({"type": "action", "action_id": 1})
        ws.receive_json()  # frame
        ws.receive_json()  # probe
        ws.send_json({"type": "action", "action_id": 5})  # clears level 1
        assert ws.receive_json()["frame_data"]["levels_completed"] == 1
        phase = ws.receive_json()
        assert (phase["phase"], phase["reason"]) == ("observe", "level_cleared")
    last = kinds(tmp_path, "phase_change")[-1]
    assert (last["phase"], last["level"]) == ("observe", 1)


def test_bad_phase_and_note_without_annotation_are_errors_not_crashes(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    with client.websocket_connect("/ws/session") as ws:
        ws.receive_json()
        ws.send_json({"type": "start", "game_id": "tst1", "record": "off"})
        ws.receive_json()
        ws.send_json({"type": "note", "text": "x"})
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "phase", "phase": "plan"})
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "action", "action_id": 1})  # play still works
        assert ws.receive_json()["type"] == "frame"


def test_heldout_game_refuses_annotation_but_plays_normally(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    with client.websocket_connect("/ws/session") as ws:
        ws.receive_json()
        ws.send_json({"type": "start", "game_id": "r11l-495a7899", "record": "lean", "annotate": True})
        err = ws.receive_json()
        assert err["type"] == "error" and "held-out" in err["message"]
        assert not list(tmp_path.glob("*"))  # nothing was created
        ws.send_json({"type": "start", "game_id": "r11l-495a7899", "record": "lean"})
        assert ws.receive_json()["type"] == "frame"


def test_games_list_carries_data_use_and_session_start_records_it(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    monkeypatch.setattr(
        server,
        "list_games",
        lambda arcade: [GameMeta(game_id=gid, source="local") for gid in ("ls20-1", "r11l-2", "custom1")],
    )
    with client.websocket_connect("/ws/session") as ws:
        games = ws.receive_json()["games"]
        assert {g["game_id"]: g["data_use"] for g in games} == {
            "ls20-1": "reference-only", "r11l-2": "heldout", "custom1": "train-ok"}
        ws.send_json({"type": "start", "game_id": "ls20-1", "record": "lean", "annotate": True})
        ws.receive_json()
        ws.receive_json()
    assert kinds(tmp_path, "session_start")[0]["data_use"] == "reference-only"


def test_unusable_policy_refuses_annotation(monkeypatch, tmp_path):
    from backend.annotations.policy import load_policy
    client = client_for(monkeypatch, tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    monkeypatch.setattr(server, "policy_from_env", lambda: load_policy(bad))
    with client.websocket_connect("/ws/session") as ws:
        ws.receive_json()
        ws.send_json({"type": "start", "game_id": "tst1", "record": "lean", "annotate": True})
        assert "unusable" in ws.receive_json()["message"]


def test_mute_flushes_pending_speech_then_drops_audio_until_unmuted(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    with client.websocket_connect("/ws/session") as ws:
        announce = start_annotated(ws)
        with client.websocket_connect(f"/ws/audio?session={announce['session_id']}") as audio:
            audio.receive_json()
            audio.receive_json()
            audio.send_text(json.dumps({"type": "audio_start"}))
            audio.send_bytes(PCM + silence(300) + speechlike(800))  # mid-sentence, then mute
            audio.send_text(json.dumps({"type": "mute", "muted": True}))
            seen = drain_until(audio, "mute")
            assert seen[-1]["muted"] is True
            audio.send_bytes(PCM + speechlike(1500))  # dropped: muted
            audio.send_bytes(b"\x02" + b"secret")  # raw audio dropped too
            audio.send_text(json.dumps({"type": "mute", "muted": False}))
            drain_until(audio, "mute")
            audio.send_text(json.dumps({"type": "audio_end"}))
            drain_until(audio, "flushed")
    evs = sidecar(tmp_path)
    assert [e["muted"] for e in evs if e["kind"] == "mute"] == [True, False]
    speech = [e for e in evs if e["kind"] == "speech"]
    assert len(speech) == 1  # only the pre-mute utterance; the muted audio never reached Whisper
    assert not list(tmp_path.glob("*.audio.webm"))  # nothing retained while muted


def test_end_flushes_last_utterance_closes_session_and_reports_files(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    with client.websocket_connect("/ws/session") as ws:
        announce = start_annotated(ws)
        with client.websocket_connect(f"/ws/audio?session={announce['session_id']}") as audio:
            audio.receive_json()
            audio.receive_json()
            audio.send_text(json.dumps({"type": "audio_start"}))
            audio.send_bytes(PCM + silence(200) + speechlike(900))  # still open: no trailing silence
            audio.send_text(json.dumps({"type": "audio_end"}))
            drain_until(audio, "flushed")
        ws.send_json({"type": "end"})
        ended = ws.receive_json()
        assert ended["type"] == "ended"
        assert ended["annotations"].endswith(".annotations.jsonl") and ended["recording"].endswith(".jsonl")
        ws.send_json({"type": "action", "action_id": 1})  # session is over
        assert ws.receive_json()["type"] == "error"
    assert [e["text"] for e in kinds(tmp_path, "speech")] == ["spoken thought"]


def test_h_then_typed_note_makes_a_hypothesis_and_y_n_set_verdicts(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    with client.websocket_connect("/ws/session") as ws:
        start_annotated(ws)
        ws.send_json({"type": "hypothesis_open"})
        state = ws.receive_json()
        assert state["type"] == "hypothesis_state" and state["pending"] is True
        ws.send_json({"type": "note", "text": "the green block opens the door"})
        assert ws.receive_json()["type"] == "note_saved"
        state = ws.receive_json()
        assert state["pending"] is False and state["selected"] == "h1"
        assert state["hypotheses"][0]["statement"] == "the green block opens the door"

        ws.send_json({"type": "action", "action_id": 1})
        ws.receive_json()
        ws.receive_json()  # frame, probe
        ws.send_json({"type": "hypothesis_verdict", "verdict": "refuted"})
        state = ws.receive_json()
        assert state["hypotheses"][0]["status"] == "refuted" and state["selected"] is None

        ws.send_json({"type": "hypothesis_verdict", "verdict": "confirmed"})  # nothing selected
        err = ws.receive_json()
        assert err["type"] == "error" and "add one first" in err["message"]

        ws.send_json({"type": "hypothesis_select", "hypothesis_id": "h1"})
        assert ws.receive_json()["selected"] == "h1"
        ws.send_json({"type": "hypothesis_verdict", "verdict": "confirmed"})  # explicit reopen
        assert ws.receive_json()["hypotheses"][0]["status"] == "confirmed"
        ws.send_json({"type": "hypothesis_select", "hypothesis_id": "h9"})
        assert ws.receive_json()["type"] == "error"
    verdicts = [(e["verdict"], e["previous"]) for e in kinds(tmp_path, "hypothesis_verdict")]
    assert verdicts == [("refuted", "open"), ("confirmed", "refuted")]
    (hyp,) = kinds(tmp_path, "hypothesis")
    assert hyp["source"] == "typed" and hyp["step_at_end"] == 0


def test_hypothesis_actions_without_annotation_are_errors(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    with client.websocket_connect("/ws/session") as ws:
        ws.receive_json()
        ws.send_json({"type": "start", "game_id": "tst1", "record": "off"})
        ws.receive_json()
        for msg in ("hypothesis_open", "hypothesis_verdict", "hypothesis_select"):
            ws.send_json({"type": msg})
            assert ws.receive_json()["type"] == "error"


def test_speech_after_h_becomes_the_statement_and_audio_socket_pushes_state(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    with client.websocket_connect("/ws/session") as ws:
        announce = start_annotated(ws)
        ws.send_json({"type": "hypothesis_open"})
        assert ws.receive_json()["pending"] is True
        with client.websocket_connect(f"/ws/audio?session={announce['session_id']}") as audio:
            audio.receive_json()
            audio.receive_json()
            audio.send_text(json.dumps({"type": "audio_start"}))
            audio.send_bytes(PCM + silence(200) + speechlike(900) + silence(1300))
            seen = drain_until(audio, "hypothesis_state")
            assert seen[-1]["selected"] == "h1" and seen[-1]["hypotheses"][0]["statement"] == "spoken thought"
    (hyp,) = kinds(tmp_path, "hypothesis")
    assert hyp["source"] == "stt"
    speech = kinds(tmp_path, "speech")[0]
    assert speech["hypothesis_id"] == "h1" and hyp["source_event_id"] == speech["event_id"]


def test_level_clear_sends_a_level_cleared_message_once_per_clear(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path, LevelStub)
    with client.websocket_connect("/ws/session") as ws:
        start_annotated(ws)
        ws.send_json({"type": "action", "action_id": 1})
        ws.receive_json()
        ws.receive_json()  # frame, probe
        ws.send_json({"type": "action", "action_id": 5})
        assert ws.receive_json()["type"] == "frame"
        assert ws.receive_json()["type"] == "phase"
        assert ws.receive_json() == {"type": "level_cleared", "level": 1}
        ws.send_json({"type": "action", "action_id": 1})  # ordinary move: frame + auto-probe only
        assert ws.receive_json()["type"] == "frame"
        assert ws.receive_json()["phase"] == "probe"
        ws.send_json({"type": "action", "action_id": 5})
        assert ws.receive_json()["type"] == "frame"
        assert ws.receive_json()["phase"] == "observe"
        assert ws.receive_json() == {"type": "level_cleared", "level": 2}


def test_add_several_hypotheses_then_mark_them_in_any_order_by_id(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    with client.websocket_connect("/ws/session") as ws:
        start_annotated(ws)
        for text in ("blue cross rotates it", "grey square is the goal", "three moves only"):
            ws.send_json({"type": "hypothesis_add", "text": f"  {text}  "})
            state = ws.receive_json()
            assert state["type"] == "hypothesis_state"
        assert [h["statement"] for h in state["hypotheses"]][-1] == "three moves only"
        assert [h["status"] for h in state["hypotheses"]] == ["open"] * 3 and state["selected"] == "h3"

        ws.send_json({"type": "hypothesis_verdict", "hypothesis_id": "h2", "verdict": "refuted"})
        state = ws.receive_json()
        assert [h["status"] for h in state["hypotheses"]] == ["open", "refuted", "open"]
        assert state["selected"] == "h3"  # marking another one does not steal focus
        ws.send_json({"type": "hypothesis_verdict", "hypothesis_id": "h1", "verdict": "confirmed"})
        assert [h["status"] for h in ws.receive_json()["hypotheses"]] == ["confirmed", "refuted", "open"]
        ws.send_json({"type": "hypothesis_verdict", "hypothesis_id": "h2", "verdict": "open"})
        assert ws.receive_json()["hypotheses"][1]["status"] == "open"  # changed my mind
        ws.send_json({"type": "hypothesis_add", "text": "   "})
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "hypothesis_verdict", "hypothesis_id": "h9", "verdict": "refuted"})
        assert ws.receive_json()["type"] == "error"
    assert [e["hypothesis_id"] for e in kinds(tmp_path, "hypothesis")] == ["h1", "h2", "h3"]
    assert len(kinds(tmp_path, "hypothesis_verdict")) == 3


def test_dictate_mode_turns_each_spoken_sentence_into_a_hypothesis_until_stopped(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    with client.websocket_connect("/ws/session") as ws:
        announce = start_annotated(ws)
        ws.send_json({"type": "hypothesis_dictate", "on": True})
        state = ws.receive_json()
        assert state["batch"] is True and state["pending"] is False
        with client.websocket_connect(f"/ws/audio?session={announce['session_id']}") as audio:
            audio.receive_json()
            audio.receive_json()
            audio.send_text(json.dumps({"type": "audio_start"}))
            for _ in range(2):  # two separate sentences
                audio.send_bytes(PCM + silence(200) + speechlike(700) + silence(1300))
            audio.send_text(json.dumps({"type": "audio_end"}))
            states = drain_until(audio, "flushed")
        assert len([m for m in states if m["type"] == "hypothesis_state"]) == 2
        ws.send_json({"type": "hypothesis_dictate", "on": False})
        assert ws.receive_json()["batch"] is False
    assert [e["hypothesis_id"] for e in kinds(tmp_path, "hypothesis")] == ["h1", "h2"]
    assert [e["on"] for e in kinds(tmp_path, "dictate")] == [True, False]
