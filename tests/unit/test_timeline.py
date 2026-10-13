import json
import os

from backend.timeline import latest_recording, load_jsonl, render_timeline, sidecar_path, timeline_for


def step(i, action=1, levels=0, state="NOT_FINISHED", data=None, ts=None):
    return {
        "schema_version": 3,
        "step_index": i,
        "action_id": action,
        "action_input": data,
        "state": state,
        "levels_completed": levels,
        "win_levels": 3,
        "timestamp": ts or f"2026-10-14T00:00:{i:02d}+00:00",
    }


def ev(kind, eid, at, **kw):
    return {
        "schema_version": 1,
        "event_id": eid,
        "t": f"2026-10-14T00:00:{at:02d}.500+00:00",
        "kind": kind,
        "step_at_end": at,
        **kw,
    }


START = {
    "schema_version": 1,
    "event_id": "e1",
    "t": "2026-10-14T00:00:00+00:00",
    "kind": "session_start",
    "game_id": "g-1",
    "data_use": "train-ok",
    "stt": "small.en",
    "record_mode": "lean",
}


def lines(md):
    return md.splitlines()


def test_thought_spanning_steps_comes_after_step_at_end_and_before_the_next_action():
    steps = [step(i, action=a) for i, a in enumerate([0, 1, 2, 3, 4, 1])]
    said = ev("speech", "e2", 4, step_at_start=2, text="it moved right", phase="probe", phase_at_end="probe")
    out = lines(render_timeline(steps, [START, said]))
    said_at = next(i for i, line in enumerate(out) if "it moved right" in line)
    assert "steps 2\u21924" in out[said_at]
    through_step_4 = next(i for i, line in enumerate(out) if line.startswith("- `steps 0\u20134`"))
    next_action = next(i for i, line in enumerate(out) if line.startswith("- `step 5`"))
    assert through_step_4 < said_at < next_action


def test_consecutive_steps_collapse_into_one_run_with_glyphs_and_clicks():
    steps = [step(0, 0), step(1, 4), step(2, 4), step(3, 6, data={"x": 5, "y": 9}), step(4, 1)]
    md = render_timeline(steps, [])
    assert "`steps 0\u20134`: RESET \u2192 \u2192 click(5,9) \u2191" in md


def test_level_clear_keeps_the_clearing_step_in_the_old_level_and_opens_the_next():
    steps = [step(0, 0), step(1), step(2, levels=1), step(3, levels=1)]
    out = lines(render_timeline(steps, []))
    h = [i for i, line in enumerate(out) if line.startswith("## ")]
    assert [out[i] for i in h] == ["## Level 1", "## Level 2 — level 1 cleared"]
    assert "`steps 0\u20132`" in " ".join(out[h[0] : h[1]])  # the clearing step (2) is listed under level 1
    assert "`step 3`" in " ".join(out[h[1] :])


def test_reset_or_level_regression_opens_a_new_attempt_section():
    steps = [step(0, 0), step(1, levels=0), step(2, 2, state="GAME_OVER"), step(3, 0), step(4)]
    md = render_timeline(steps, [])
    assert "## Level 1 (after reset)" in md and "**GAME_OVER**" in md


def test_hypotheses_get_a_summary_table_and_verdict_lines():
    events = [
        START,
        ev("hypothesis", "e2", 1, hypothesis_id="h1", statement="blue cross | rotates it", source="typed"),
        ev("hypothesis", "e3", 1, hypothesis_id="h2", statement="goal is grey", source="stt"),
        ev("hypothesis_verdict", "e4", 3, hypothesis_id="h1", verdict="refuted", previous="open"),
        ev("hypothesis_verdict", "e5", 4, hypothesis_id="h2", verdict="confirmed", previous="open"),
        ev("hypothesis_verdict", "e6", 5, hypothesis_id="h2", verdict="open", previous="confirmed"),
    ]
    md = render_timeline([step(i) for i in range(6)], events)
    assert "| h1 | FALSE | 1 | 3 | blue cross \\| rotates it |" in md  # pipe escaped for the table
    assert "| h2 | open | 1 |  | goal is grey |" in md  # reopened: no decided step
    assert "**h1 → FALSE** (was open)" in md and "**h2 proposed**" in md


def test_speech_shows_hypothesis_tag_and_phase_change_over_the_sentence():
    said = ev(
        "speech",
        "e2",
        1,
        step_at_start=1,
        text="back to observing",
        phase="reflect",
        phase_at_end="observe",
        hypothesis_id="h3",
    )
    md = render_timeline([step(0), step(1)], [START, said])
    assert "(reflect→observe, step 1): [h3] back to observing" in md


def test_ignored_events_are_hidden_and_counted():
    keep = ev("speech", "e2", 1, step_at_start=1, text="real thought", phase="probe")
    drop = ev(
        "speech", "e3", 1, step_at_start=1, text="reading the instructions aloud", phase="probe", ignore=True
    )
    md = render_timeline([step(0), step(1)], [START, keep, drop])
    assert "real thought" in md and "reading the instructions" not in md
    assert "1 annotation event(s) marked `ignore` are hidden" in md


def test_unknown_event_kinds_are_shown_not_dropped_or_crashed_on():
    md = render_timeline([step(0)], [START, ev("brand_new_kind", "e2", 0, foo="bar")])
    assert '- [brand_new_kind] {"kind": "brand_new_kind", "step_at_end": 0, "foo": "bar"}' in md


def test_missing_sidecar_gives_a_moves_only_timeline(tmp_path):
    rec = tmp_path / "local.g-1.lean.20261014T000000Z.recording.jsonl"
    rec.write_text("\n".join(json.dumps(step(i)) for i in range(3)))
    md = timeline_for(rec)
    assert "No annotations file" in md and "`steps 0–2`" in md


def test_truncated_final_line_is_skipped_and_reported(tmp_path):
    rec = tmp_path / "local.g-1.lean.20261014T000000Z.recording.jsonl"
    rec.write_text(json.dumps(step(0)) + "\n" + json.dumps(step(1)) + '\n{"step_index": 2, "act')
    rows, skipped = load_jsonl(rec)
    assert len(rows) == 2 and skipped == 1
    assert "1 unreadable line(s) skipped" in timeline_for(rec)


def test_v1_v2_and_v3_recordings_all_render(tmp_path):
    rec = tmp_path / "local.g-1.lean.20261014T000000Z.recording.jsonl"
    v1 = {
        "schema_version": 1,
        "step_index": 0,
        "action_id": 0,
        "action_input": None,
        "state": "NOT_FINISHED",
        "levels_completed": 0,
        "timestamp": "2026-10-14T00:00:00+00:00",
    }  # no mode, no frame_sha256
    v2 = {**v1, "schema_version": 2, "step_index": 1, "action_id": 1, "mode": "lean"}
    rec.write_text("\n".join(json.dumps(r) for r in (v1, v2, step(2, action=4))))
    md = timeline_for(rec)
    assert md.count("## Level 1") == 1
    assert "`steps 0\u20132`: RESET \u2191 \u2192" in md


def test_sidecar_naming(tmp_path):
    rec = tmp_path / "local.a.lean.20261014T000001Z.recording.jsonl"
    assert sidecar_path(rec).name == "local.a.lean.20261014T000001Z.annotations.jsonl"


def test_latest_recording_prefers_annotated_sessions_then_newest(tmp_path):
    a = tmp_path / "local.a.lean.20261014T000001Z.recording.jsonl"
    b = tmp_path / "local.b.lean.20261014T000002Z.recording.jsonl"
    a.write_text("{}")
    b.write_text("{}")
    sidecar_path(a).write_text("{}")  # only `a` has annotations
    os.utime(a, (1, 1))
    os.utime(b, (2, 2))  # b is the newer file
    assert latest_recording(tmp_path) == a
    sidecar_path(a).unlink()
    assert latest_recording(tmp_path) == b


def test_latest_recording_in_an_empty_directory_is_none(tmp_path):
    assert latest_recording(tmp_path) is None
