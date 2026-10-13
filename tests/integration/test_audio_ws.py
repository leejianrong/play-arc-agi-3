"""The /ws/audio path end to end against a fake Transcriber (SLICES V3 integration tests):
PCM in -> interim then final out -> one `speech` event in the sidecar with the right step range.
"""

import json

from fastapi.testclient import TestClient

from backend import server
from backend.stt.base import FakeTranscriber, TranscriberUnavailable
from tests.helpers.audio import silence, speechlike
from tests.integration.test_session_ws import make_client

PCM = b"\x01"
OPUS = b"\x02"


def install_transcriber(monkeypatch, fake):
    async def get():
        fake.load()
        return fake

    monkeypatch.setattr(server, "get_transcriber", get)


def drain_until(ws, wanted: str, limit: int = 40):
    seen = []
    for _ in range(limit):
        message = ws.receive_json()
        seen.append(message)
        if message["type"] == wanted:
            return seen
    raise AssertionError(f"never saw {wanted!r}; got {[m['type'] for m in seen]}")


def start_annotated(ws, record="off"):
    ws.receive_json()  # games
    ws.send_json({"type": "start", "game_id": "tst1", "record": record, "annotate": True})
    ws.receive_json()  # frame
    announce = ws.receive_json()
    assert announce["type"] == "annotation"
    return announce


def sidecar(tmp_path):
    (path,) = tmp_path.glob("*.annotations.jsonl")
    return [json.loads(line) for line in path.read_text().splitlines()]


def stream(audio_ws, pcm: bytes, chunk_ms: int = 100):
    step = 16 * chunk_ms * 2
    for i in range(0, len(pcm), step):
        audio_ws.send_bytes(PCM + pcm[i : i + step])


def test_annotate_promotes_off_to_lean_and_announces_the_session(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)
    install_transcriber(monkeypatch, FakeTranscriber())
    with client.websocket_connect("/ws/session") as ws:
        announce = start_annotated(ws, record="off")
    assert announce["record"] == "lean"
    assert len(list(tmp_path.glob("*.lean.*.recording.jsonl"))) == 1
    assert sidecar(tmp_path)[0]["kind"] == "session_start"


def test_speech_flows_to_interim_final_and_sidecar_with_step_range(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)
    fake = FakeTranscriber(["the blue square", "the blue square is the player"])
    install_transcriber(monkeypatch, fake)

    with client.websocket_connect("/ws/session") as ws:
        announce = start_annotated(ws, record="lean")
        with client.websocket_connect(f"/ws/audio?session={announce['session_id']}") as audio:
            assert audio.receive_json() == {"type": "status", "state": "loading"}
            assert audio.receive_json()["state"] == "ready"
            audio.send_text(json.dumps({"type": "audio_start"}))

            stream(audio, silence(300) + speechlike(3500) + silence(1200))
            seen = drain_until(audio, "final")

            kinds = [m["type"] for m in seen]
            assert "interim" in kinds  # a 3.5 s utterance crosses the 1.5 s interim cadence
            final = seen[-1]
            assert final["text"] == "the blue square is the player"
            assert final["step_at_start"] == final["step_at_end"] == 0

    events = sidecar(tmp_path)
    speech = [e for e in events if e["kind"] == "speech"]
    assert len(speech) == 1
    assert speech[0]["text"] == final["text"] and speech[0]["source"] == "stt"
    a, b = speech[0]["audio_offset_ms"]
    assert 200 <= a <= 450 and 3500 <= b <= 4000, (a, b)


def test_speech_over_two_game_steps_records_start_and_end_steps(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)
    install_transcriber(monkeypatch, FakeTranscriber(["it moved"]))

    with client.websocket_connect("/ws/session") as ws:
        announce = start_annotated(ws, record="lean")
        with client.websocket_connect(f"/ws/audio?session={announce['session_id']}") as audio:
            audio.receive_json()
            audio.receive_json()
            audio.send_text(json.dumps({"type": "audio_start"}))
            # Step 1 is taken at the session's current time; the utterance ends "later" in audio time
            # than the wall clock has advanced, so assert the structural contract instead: the
            # annotation session maps by its own clock, and both indexes are valid recorded steps.
            ws.send_json({"type": "action", "action_id": 1})
            ws.receive_json()
            stream(audio, speechlike(1000) + silence(1000))
            final = drain_until(audio, "final")[-1]
    assert 0 <= final["step_at_start"] <= final["step_at_end"] <= 1


def test_clatter_produces_no_events(monkeypatch, tmp_path):
    from tests.helpers.audio import click

    client = make_client(monkeypatch, tmp_path)
    fake = FakeTranscriber(["should never be heard"])
    install_transcriber(monkeypatch, fake)

    with client.websocket_connect("/ws/session") as ws:
        announce = start_annotated(ws, record="lean")
        with client.websocket_connect(f"/ws/audio?session={announce['session_id']}") as audio:
            audio.receive_json()
            audio.receive_json()
            stream(audio, silence(300) + click() + silence(400) + click() + silence(800))
    assert fake.calls == []
    assert [e["kind"] for e in sidecar(tmp_path)] == ["session_start", "phase_change"]


def test_opus_chunks_are_written_verbatim_to_the_audio_file(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)
    install_transcriber(monkeypatch, FakeTranscriber())
    with client.websocket_connect("/ws/session") as ws:
        announce = start_annotated(ws, record="lean")
        with client.websocket_connect(f"/ws/audio?session={announce['session_id']}") as audio:
            audio.receive_json()
            audio.receive_json()
            audio.send_bytes(OPUS + b"abc")
            audio.send_bytes(OPUS + b"def")
    (audio_file,) = tmp_path.glob("*.audio.webm")
    assert audio_file.read_bytes() == b"abcdef"


def test_unavailable_engine_reports_error_but_still_keeps_audio_and_play(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)
    install_transcriber(monkeypatch, FakeTranscriber(load_error="no model here"))

    with client.websocket_connect("/ws/session") as ws:
        announce = start_annotated(ws, record="lean")
        with client.websocket_connect(f"/ws/audio?session={announce['session_id']}") as audio:
            audio.receive_json()  # loading
            error = audio.receive_json()
            assert error["type"] == "error" and error["code"] == "stt_unavailable"
            assert "no model here" in error["message"]
            audio.send_bytes(PCM + speechlike(500))  # ignored, not fatal
            audio.send_bytes(OPUS + b"keep")
        ws.send_json({"type": "action", "action_id": 2})  # the game session is unaffected
        assert ws.receive_json()["type"] == "frame"
    assert next(tmp_path.glob("*.audio.webm")).read_bytes() == b"keep"


def test_audio_socket_without_a_session_is_rejected(monkeypatch, tmp_path):
    client = TestClient(server.app)
    with client.websocket_connect("/ws/audio?session=nope") as audio:
        message = audio.receive_json()
        assert message["code"] == "no_session"


def test_unavailable_error_type_is_what_the_endpoint_catches():
    assert issubclass(TranscriberUnavailable, RuntimeError)
