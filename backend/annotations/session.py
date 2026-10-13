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
        self._write(
            {
                "kind": "session_start",
                "game_id": game_id,
                "record_mode": record_mode,
                "recording": recording_path.name,
                "stt": stt,
                "audio": self.audio_path.name if keep_audio else None,
                "data_use": "unclassified",  # ADR-0009 labels arrive with slice V4
            },
            at_ms=0,
        )
        _ACTIVE[self.session_id] = self

    def now_ms(self) -> int:
        return int((time.monotonic() - self._t0) * 1000)

    def mark_step(self, step_index: int, levels_completed: int) -> None:
        self._step_ms.append(self.now_ms())
        self._steps.append((step_index, levels_completed))

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
        return self._write(
            {
                "kind": "speech",
                "source": "stt",
                "text": text,
                "step_at_start": start_step,
                "step_at_end": end_step,
                "level": level,
                "phase": None,  # V4
                "hypothesis_id": None,  # V5
                "audio_offset_ms": list(audio_offset_ms),
            },
            at_ms=end_ms,
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
