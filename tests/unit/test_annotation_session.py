import json

from backend.annotations.session import AnnotationSession, get_session


def make(tmp_path, **kw):
    rec = tmp_path / "local.tst1.lean.20261014T000000Z.recording.jsonl"
    return AnnotationSession(rec, "tst1", "lean", stt="fake", **kw)


def events(session):
    return [json.loads(line) for line in session.path.read_text().splitlines()]


def test_files_share_the_recordings_stem(tmp_path):
    s = make(tmp_path)
    assert s.path.name == "local.tst1.lean.20261014T000000Z.annotations.jsonl"
    assert s.audio_path.name == "local.tst1.lean.20261014T000000Z.audio.webm"


def test_first_line_is_session_start_and_every_line_is_versioned_and_ordered(tmp_path):
    s = make(tmp_path)
    s.speech("hello", 100, 200, (0, 100))
    s.speech("again", 300, 400, (200, 300))
    evs = events(s)
    assert evs[0]["kind"] == "session_start"
    assert evs[0]["data_use"] == "unclassified"
    assert evs[0]["game_id"] == "tst1"
    assert [e["event_id"] for e in evs] == ["e1", "e2", "e3", "e4"]
    assert evs[1]["kind"] == "phase_change" and evs[1]["phase"] == "observe"
    assert all(e["schema_version"] == 1 for e in evs)


def test_speech_spanning_steps_records_both_indexes_and_level(tmp_path, monkeypatch):
    s = make(tmp_path)
    s._step_ms, s._steps = [0, 1000, 2000, 3000], [(0, 0), (1, 0), (2, 1), (3, 1)]
    event = s.speech("it moved", start_ms=1200, end_ms=2500, audio_offset_ms=(1200, 2500))
    assert (event["step_at_start"], event["step_at_end"], event["level"]) == (1, 2, 1)
    assert event["audio_offset_ms"] == [1200, 2500]
    assert event["source"] == "stt" and event["kind"] == "speech"


def test_step_at_before_any_step_is_zero_and_before_first_mark_clamps(tmp_path):
    s = make(tmp_path)
    assert s.step_at(500) == (0, 0)
    s._step_ms, s._steps = [100], [(0, 0)]
    assert s.step_at(50) == (0, 0)


def test_mark_step_uses_the_live_clock(tmp_path):
    s = make(tmp_path)
    s.mark_step(0, 0)
    s.mark_step(1, 0)
    assert s.step_at(s.now_ms() + 10)[0] == 1


def test_audio_written_verbatim_and_can_be_disabled(tmp_path):
    s = make(tmp_path)
    s.write_audio(b"abc")
    s.write_audio(b"def")
    assert s.audio_path.read_bytes() == b"abcdef"
    off = AnnotationSession(tmp_path / "x.recording.jsonl", "g", "lean", stt=None, keep_audio=False)
    off.write_audio(b"zzz")
    assert not off.audio_path.exists()


def test_registry_lookup_and_close(tmp_path):
    s = make(tmp_path)
    assert get_session(s.session_id) is s
    s.close()
    assert get_session(s.session_id) is None


def test_h_then_note_creates_hypothesis_event_linked_to_its_source(tmp_path):
    s = make(tmp_path)
    s.mark_step(0, 0)
    s.toggle_hypothesis()
    note = s.note("the green block opens the door")
    evs = events(s)
    hyp = [e for e in evs if e["kind"] == "hypothesis"]
    assert len(hyp) == 1
    assert hyp[0]["hypothesis_id"] == "h1" and hyp[0]["statement"] == "the green block opens the door"
    assert hyp[0]["source"] == "typed" and hyp[0]["source_event_id"] == note["event_id"]
    assert note["hypothesis_id"] == "h1"  # the statement is itself filed under the hypothesis


def test_verdict_event_links_to_the_step_and_later_events_are_tagged(tmp_path):
    s = make(tmp_path)
    s.mark_step(0, 0)
    s.toggle_hypothesis()
    s.note("door opens with green")
    s.mark_step(1, 0, is_action=True)
    s.mark_step(2, 0, is_action=True)
    state = s.verdict("refuted")
    evs = events(s)
    v = [e for e in evs if e["kind"] == "hypothesis_verdict"][0]
    assert (v["hypothesis_id"], v["verdict"], v["previous"], v["step_at_end"]) == ("h1", "refuted", "open", 2)
    assert state["hypotheses"][0]["status"] == "refuted" and state["selected"] is None
    assert s.note("what now")["hypothesis_id"] is None  # nothing selected after the only one closed


def test_speech_is_tagged_with_the_hypothesis_selected_when_it_began(tmp_path):
    s = make(tmp_path)
    clock = {"ms": 0}
    s.now_ms = lambda: clock["ms"]  # scripted time: the order of events is the point of this test
    s.mark_step(0, 0)
    s.toggle_hypothesis()
    clock["ms"] = 100
    s.note("a")  # h1 selected from t=100
    clock["ms"] = 300
    s.verdict("refuted")  # N pressed at t=300, before the sentence below was transcribed
    late = s.speech("no it did not", start_ms=200, end_ms=250, audio_offset_ms=(0, 50))
    assert late["hypothesis_id"] == "h1"


def test_speech_while_armed_becomes_the_statement(tmp_path):
    s = make(tmp_path)
    s.mark_step(0, 0)
    s.toggle_hypothesis()
    now = s.now_ms()
    ev = s.speech("the red thing is the goal", now + 10, now + 900, (0, 890))
    hyp = [e for e in events(s) if e["kind"] == "hypothesis"][0]
    assert hyp["source"] == "stt" and hyp["source_event_id"] == ev["event_id"] and ev["hypothesis_id"] == "h1"
    assert s.hypothesis_state()["pending"] is False
