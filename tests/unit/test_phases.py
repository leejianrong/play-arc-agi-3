import pytest

from backend.annotations.phases import PhaseMachine


def test_starts_in_observe_with_a_session_start_event():
    m = PhaseMachine()
    assert m.phase == "observe"
    ev = m.start_event()
    assert (ev.phase, ev.previous, ev.reason) == ("observe", None, "session_start")


def test_first_action_in_observe_auto_advances_to_probe_once():
    m = PhaseMachine()
    change = m.on_frame(is_action=True, levels_completed=0, at_ms=100)
    assert (change.phase, change.previous, change.reason) == ("probe", "observe", "auto_first_action")
    assert m.on_frame(True, 0, 200) is None  # no further automatic transitions
    assert m.phase == "probe"


def test_a_non_action_frame_never_advances():
    m = PhaseMachine()
    assert m.on_frame(False, 0, 10) is None and m.phase == "observe"


@pytest.mark.parametrize("phase", ["plan", "execute"])
def test_actions_do_not_leave_plan_or_execute(phase):
    m = PhaseMachine()
    m.set(phase, 10)
    assert m.on_frame(True, 0, 30) is None
    assert m.phase == phase


@pytest.mark.parametrize("phase", ["observe", "reflect"])
def test_first_action_leaves_observe_and_reflect_for_probe(phase):
    # Reflect is between-level talk: touching the game ends it, so it can't strand the label.
    m = PhaseMachine()
    m.set(phase, 10)
    change = m.on_frame(True, 0, 30)
    assert (change.phase, change.reason) == ("probe", "auto_first_action")


def test_level_clear_returns_to_observe_and_beats_the_auto_probe():
    m = PhaseMachine()
    m.set("execute", 10)
    change = m.on_frame(True, levels_completed=1, at_ms=50)
    assert (change.phase, change.reason) == ("observe", "level_cleared")
    assert m.phase == "observe"  # the clearing action does not immediately flip to probe


def test_first_frame_baseline_is_not_a_level_clear():
    m = PhaseMachine()
    m.baseline(3)
    assert m.on_frame(False, 3, 0) is None


def test_manual_set_validates_and_ignores_no_ops():
    m = PhaseMachine()
    with pytest.raises(ValueError):
        m.set("daydream", 1)
    assert m.set("observe", 1) is None
    assert m.set("plan", 2).reason == "manual"


def test_phase_at_reads_history_by_time():
    m = PhaseMachine()
    m.on_frame(True, 0, 1000)  # -> probe at 1000
    m.set("plan", 2000)
    assert [m.phase_at(t) for t in (0, 999, 1000, 1999, 2000, 9999)] == [
        "observe", "observe", "probe", "probe", "plan", "plan",
    ]
