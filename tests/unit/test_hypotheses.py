import pytest

from backend.annotations.hypotheses import HypothesisError, HypothesisRegistry


def stated(reg, text="x", at=100, step=1, level=0):
    reg.arm(at - 1)
    return reg.capture(text, at, step, level)


def test_ids_are_stable_and_sequential_and_new_one_is_selected():
    reg = HypothesisRegistry()
    a, b = stated(reg, "a", 10), stated(reg, "b", 20)
    assert (a.id, b.id) == ("h1", "h2")
    assert reg.selected == "h2" and a.status == "open"


def test_registries_do_not_share_ids_or_state():
    one, two = HypothesisRegistry(), HypothesisRegistry()
    stated(one)
    assert two.items == {} and stated(two).id == "h1"


def test_arming_is_idempotent_cancel_is_explicit_and_capture_clears_it():
    reg = HypothesisRegistry()
    reg.arm(5)
    assert reg.pending
    reg.arm(6)  # a second H must NOT cancel: the first sentence may not be transcribed yet
    assert reg.pending and reg._armed_since == 5
    reg.cancel(7)
    assert not reg.pending
    reg.arm(8)
    reg.capture("idea", 9, 0, 0)
    assert not reg.pending


def test_captures_only_when_armed_and_utterance_ends_after_the_press():
    reg = HypothesisRegistry()
    assert not reg.captures(1000, "stt")  # not armed
    reg.arm(500)
    assert not reg.captures(499, "stt")  # finished before H: not this hypothesis' statement
    assert reg.captures(500, "stt") and reg.captures(9000, "typed")  # in progress at the press, or later


def test_verdict_applies_to_selected_then_selection_moves_to_latest_other_open():
    reg = HypothesisRegistry()
    stated(reg, "a", 10)
    stated(reg, "b", 20)
    stated(reg, "c", 30)
    h, prev = reg.verdict("refuted", 40)  # c is selected
    assert (h.id, h.status, prev) == ("h3", "refuted", "open")
    assert reg.selected == "h2"  # most recent still-open
    reg.verdict("confirmed", 50)
    assert reg.selected == "h1"
    reg.verdict("confirmed", 60)
    assert reg.selected is None
    assert [x.status for x in reg.items.values()] == ["confirmed", "confirmed", "refuted"]


def test_verdict_without_selection_or_with_bad_value_is_a_clear_error():
    reg = HypothesisRegistry()
    with pytest.raises(HypothesisError, match="add one first"):
        reg.verdict("confirmed", 1)
    stated(reg)
    with pytest.raises(HypothesisError):
        reg.verdict("maybe", 2)


def test_selecting_a_closed_hypothesis_allows_an_explicit_second_verdict():
    reg = HypothesisRegistry()
    stated(reg, "a", 10)
    reg.verdict("refuted", 20)
    reg.select("h1", 30)
    h, prev = reg.verdict("confirmed", 40)
    assert (h.status, prev) == ("confirmed", "refuted")


def test_select_unknown_id_is_an_error():
    with pytest.raises(HypothesisError):
        HypothesisRegistry().select("h9", 1)


def test_selected_at_reads_history_so_late_transcripts_get_the_right_tag():
    reg = HypothesisRegistry()
    stated(reg, "a", 100)
    stated(reg, "b", 200)
    reg.verdict("refuted", 300)  # selection falls back to h1 at t=300
    assert [reg.selected_at(t) for t in (0, 99, 100, 199, 200, 299, 300, 999)] == [
        None, None, "h1", "h1", "h2", "h2", "h1", "h1",
    ]


def test_version_bumps_on_every_change_and_state_snapshot_shape():
    reg = HypothesisRegistry()
    v0 = reg.version
    stated(reg, "a", 10)
    assert reg.version > v0
    state = reg.state()
    assert state["selected"] == "h1" and state["pending"] is False
    assert state["hypotheses"][0] == {"id": "h1", "statement": "a", "status": "open", "step": 1, "level": 0}


def test_verdict_by_id_does_not_need_selection_and_keeps_the_current_selection():
    reg = HypothesisRegistry()
    stated(reg, "a", 10)
    stated(reg, "b", 20)
    stated(reg, "c", 30)  # c selected: "currently testing"
    h, prev = reg.verdict("refuted", 40, hypothesis_id="h1")
    assert (h.id, h.status, prev) == ("h1", "refuted", "open")
    assert reg.selected == "h3"  # marking another one does not steal focus
    reg.verdict("confirmed", 50, hypothesis_id="h2")
    assert [x.status for x in reg.items.values()] == ["refuted", "confirmed", "open"]


def test_marking_the_selected_one_by_id_still_moves_focus_on():
    reg = HypothesisRegistry()
    stated(reg, "a", 10)
    stated(reg, "b", 20)
    reg.verdict("refuted", 30, hypothesis_id="h2")
    assert reg.selected == "h1"


def test_open_verdict_un_decides_and_focuses_it():
    reg = HypothesisRegistry()
    stated(reg, "a", 10)
    reg.verdict("confirmed", 20)
    h, prev = reg.verdict("open", 30, hypothesis_id="h1")
    assert (h.status, prev, reg.selected) == ("open", "confirmed", "h1")


def test_unknown_id_in_verdict_is_an_error():
    with pytest.raises(HypothesisError):
        HypothesisRegistry().verdict("confirmed", 1, hypothesis_id="h7")


def test_dictate_mode_captures_every_sentence_but_not_typed_notes_until_stopped():
    reg = HypothesisRegistry()
    reg.set_batch(True, 100)
    assert reg.batch and not reg.pending  # the one-shot "listening" state is separate
    assert reg.captures(200, "stt") and not reg.captures(200, "typed")
    reg.capture("one", 200, 0, 0)
    assert reg.captures(300, "stt")  # still armed after a capture
    reg.capture("two", 300, 0, 0)
    reg.set_batch(False, 400)
    assert not reg.captures(500, "stt") and list(reg.items) == ["h1", "h2"]


def test_arming_while_dictating_changes_nothing_and_cancel_stops_dictating():
    reg = HypothesisRegistry()
    reg.set_batch(True, 1)
    reg.arm(2)
    assert reg.batch and not reg.pending
    reg.cancel(3)
    assert not reg.batch and reg.state()["batch"] is False
