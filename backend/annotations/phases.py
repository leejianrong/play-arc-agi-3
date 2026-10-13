"""Play-phase state machine (ADR-0008).

Phases: observe (hands off), probe (touching the game to test something), plan, execute, reflect.
A level starts in `observe`. The first game action while observing flips to `probe`, since touching
the game is the signal. Clearing a level returns to `observe`. Everything else is declared by the
player. Phase is a label, never a lock: no input is ever blocked.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

PHASES = ("observe", "probe", "plan", "execute", "reflect")


@dataclass(frozen=True, slots=True)
class PhaseChange:
    phase: str
    previous: str | None
    reason: str  # session_start | auto_first_action | level_cleared | manual


class PhaseMachine:
    def __init__(self, levels_completed: int = 0) -> None:
        self.phase = "observe"
        self._levels = levels_completed
        self._ms: list[int] = [0]
        self._history: list[str] = ["observe"]

    def baseline(self, levels_completed: int) -> None:
        """The first observed frame sets the level count; it is not a level clear."""
        self._levels = levels_completed

    def start_event(self) -> PhaseChange:
        return PhaseChange("observe", None, "session_start")

    def on_frame(self, is_action: bool, levels_completed: int, at_ms: int) -> PhaseChange | None:
        """Call after every recorded step. Returns the change it caused, if any."""
        cleared = levels_completed > self._levels
        self._levels = levels_completed
        if cleared:
            return self._set("observe", "level_cleared", at_ms)
        if is_action and self.phase == "observe":
            return self._set("probe", "auto_first_action", at_ms)
        return None

    def set(self, phase: str, at_ms: int) -> PhaseChange | None:
        if phase not in PHASES:
            raise ValueError(f"unknown phase {phase!r}")
        if phase == self.phase:
            return None
        return self._set(phase, "manual", at_ms)

    def phase_at(self, ms: int) -> str:
        i = bisect.bisect_right(self._ms, ms) - 1
        return self._history[max(i, 0)]

    def _set(self, phase: str, reason: str, at_ms: int) -> PhaseChange | None:
        if phase == self.phase:
            return None
        previous, self.phase = self.phase, phase
        self._ms.append(at_ms)
        self._history.append(phase)
        return PhaseChange(phase, previous, reason)
