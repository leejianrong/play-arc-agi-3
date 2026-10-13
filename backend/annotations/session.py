"""Annotation sidecar writer and step clock (ADR-0007).

One AnnotationSession per annotated play session. It owns three things that must agree:
the sidecar JSONL, the raw audio file, and a clock mapping session time -> recorded step, so a
thought spoken over steps 12-14 is stored with step_at_start=12, step_at_end=14.
"""

from __future__ import annotations

import bisect
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .hypotheses import HypothesisRegistry
from .phases import PhaseChange, PhaseMachine

SCHEMA_VERSION = 1

_ACTIVE: dict[str, AnnotationSession] = {}


def get_session(session_id: str) -> AnnotationSession | None:
    return _ACTIVE.get(session_id)


class AnnotationSession:
    def __init__(
        self,
        recording_path: Path,
        game_id: str,
        record_mode: str,
        stt: str | None,
        keep_audio: bool = True,
        data_use: str = "unclassified",
    ) -> None:
        stem = recording_path.name.removesuffix(".recording.jsonl")
        self.path = recording_path.with_name(f"{stem}.annotations.jsonl")
        self.audio_path = recording_path.with_name(f"{stem}.audio.webm")
        self.keep_audio = keep_audio
        self.session_id = uuid.uuid4().hex[:12]
        self._t0 = time.monotonic()
        self._started_at = datetime.now(UTC)
        self._event_seq = 0
        self._step_ms: list[int] = []
        self._steps: list[tuple[int, int]] = []  # (step_index, level) parallel to _step_ms
        self.phases = PhaseMachine()
        self.hyp = HypothesisRegistry()
        self.muted = False
        self._write(
            {
                "kind": "session_start",
                "game_id": game_id,
                "record_mode": record_mode,
                "recording": recording_path.name,
                "stt": stt,
                "audio": self.audio_path.name if keep_audio else None,
                "data_use": data_use,
            },
            at_ms=0,
        )
        self._write_phase_change(self.phases.start_event(), at_ms=0)
        _ACTIVE[self.session_id] = self

    def now_ms(self) -> int:
        return int((time.monotonic() - self._t0) * 1000)

    def mark_step(
        self, step_index: int, levels_completed: int, is_action: bool = False
    ) -> PhaseChange | None:
        """Record that a step happened now; returns the phase change it caused, if any."""
        now = self.now_ms()
        first = not self._steps
        self._step_ms.append(now)
        self._steps.append((step_index, levels_completed))
        if first:
            self.phases.baseline(levels_completed)
            return None
        change = self.phases.on_frame(is_action, levels_completed, now)
        if change is not None:
            self._write_phase_change(change, at_ms=now)
        return change

    def set_phase(self, phase: str) -> PhaseChange | None:
        now = self.now_ms()
        change = self.phases.set(phase, now)
        if change is not None:
            self._write_phase_change(change, at_ms=now)
        return change

    def note(self, text: str) -> dict:
        now = self.now_ms()
        step, level = self.step_at(now)
        captured = self._capture(text, now, step, level)
        event = self._write(
            {
                "kind": "text",
                "source": "typed",
                "text": text,
                "step_at_start": step,
                "step_at_end": step,
                "level": level,
                "phase": self.phases.phase,
                "hypothesis_id": captured.id if captured else self.hyp.selected_at(now),
            },
            at_ms=now,
        )
        self._write_hypothesis(captured, event, "typed", now)
        return event

    def set_muted(self, muted: bool) -> dict | None:
        if muted == self.muted:
            return None
        self.muted = muted
        now = self.now_ms()
        step, level = self.step_at(now)
        return self._write(
            {"kind": "mute", "muted": muted, "step_at_end": step, "level": level,
             "phase": self.phases.phase},
            at_ms=now,
        )

    def _write_phase_change(self, change: PhaseChange, at_ms: int) -> dict:
        step, level = self.step_at(at_ms)
        return self._write(
            {
                "kind": "phase_change",
                "phase": change.phase,
                "previous": change.previous,
                "reason": change.reason,
                "step_at_end": step,
                "level": level,
            },
            at_ms=at_ms,
        )

    def step_at(self, ms: int) -> tuple[int, int]:
        """(step_index, level) in effect at session time `ms`; the first step if none yet."""
        if not self._steps:
            return (0, 0)
        i = bisect.bisect_right(self._step_ms, ms) - 1
        return self._steps[max(i, 0)]

    def speech(
        self, text: str, start_ms: int, end_ms: int, audio_offset_ms: tuple[int, int]
    ) -> dict:
        start_step, _ = self.step_at(start_ms)
        end_step, level = self.step_at(end_ms)
        captured = self._capture(text, end_ms, end_step, level, end_ms=end_ms)
        event = self._write(
            {
                "kind": "speech",
                "source": "stt",
                "text": text,
                "step_at_start": start_step,
                "step_at_end": end_step,
                "level": level,
                "phase": self.phases.phase_at(start_ms),
                "hypothesis_id": captured.id if captured else self.hyp.selected_at(start_ms),
                "audio_offset_ms": list(audio_offset_ms),
            },
            at_ms=end_ms,
        )
        self._write_hypothesis(captured, event, "stt", end_ms)
        return event

    # -- hypotheses (ADR-0008) ------------------------------------------------------------

    def hypothesis_state(self) -> dict:
        return self.hyp.state()

    def toggle_hypothesis(self) -> dict:
        self.hyp.toggle_pending(self.now_ms())
        return self.hyp.state()

    def select_hypothesis(self, hypothesis_id: str) -> dict:
        self.hyp.select(hypothesis_id, self.now_ms())
        return self.hyp.state()

    def verdict(self, verdict: str) -> dict:
        now = self.now_ms()
        h, previous = self.hyp.verdict(verdict, now)
        step, level = self.step_at(now)
        self._write(
            {
                "kind": "hypothesis_verdict",
                "hypothesis_id": h.id,
                "verdict": verdict,
                "previous": previous,
                "step_at_end": step,
                "level": level,
                "phase": self.phases.phase,
            },
            at_ms=now,
        )
        return self.hyp.state()

    def _capture(self, text, now_ms, step, level, end_ms=None):
        if not self.hyp.captures(now_ms if end_ms is None else end_ms):
            return None
        return self.hyp.capture(text, now_ms, step, level)

    def _write_hypothesis(self, captured, source_event, source, at_ms) -> None:
        if captured is None:
            return
        self._write(
            {
                "kind": "hypothesis",
                "hypothesis_id": captured.id,
                "statement": captured.statement,
                "source": source,
                "source_event_id": source_event["event_id"],
                "step_at_end": captured.step,
                "level": captured.level,
                "phase": self.phases.phase_at(at_ms),
            },
            at_ms=at_ms,
        )

    def write_audio(self, chunk: bytes) -> None:
        if not self.keep_audio:
            return
        with open(self.audio_path, "ab") as f:
            f.write(chunk)

    def close(self) -> None:
        _ACTIVE.pop(self.session_id, None)

    def _write(self, fields: dict, at_ms: int) -> dict:
        self._event_seq += 1
        event = {
            "schema_version": SCHEMA_VERSION,
            "event_id": f"e{self._event_seq}",
            "t": (self._started_at + timedelta(milliseconds=at_ms)).isoformat(),
            **fields,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            json.dump(event, f)
            f.write("\n")
        return event
