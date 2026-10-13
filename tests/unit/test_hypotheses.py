import pytest

from backend.annotations.hypotheses import HypothesisError, HypothesisRegistry


def stated(reg, text="x", at=100, step=1, level=0):
    reg.toggle_pending(at - 1)
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


def test_h_toggles_pending_and_capture_clears_it():
    reg = HypothesisRegistry()
    assert reg.toggle_pending(5) is True and reg.pending
    assert reg.toggle_pending(6) is False and not reg.pending  # pressing H again cancels
    reg.toggle_pending(7)
    reg.capture("idea", 8, 0, 0)
    assert not reg.pending


def test_captures_only_when_armed_and_utterance_ends_after_the_press():
    reg = HypothesisRegistry()
    assert not reg.captures(1000)  # not armed
    reg.toggle_pending(500)
    assert not reg.captures(499)  # finished before H: not this hypothesis' statement
    assert reg.captures(500) and reg.captures(9000)  # in progress at the press, or later


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
    with pytest.raises(HypothesisError, match="press H"):
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
