"""Append-only JSONL session recorder (ADR-0003, ADR-0005).

One file per session, one line per step (including the initial reset), each
line fully self-describing via schema_version so a future reader never needs
a separate file header.

Recording is opt-in (ADR-0005): the caller only constructs a Recorder when
the user asked for one. Two modes:

- "full": every line carries the actual frame grid, exactly like before.
  Self-contained, but a real game's frames dominate file size.
- "lean": every line carries the same metadata but omits the frame grid.
  Since real games are deterministic (confirmed in ADR-0005 -- no
  randomness anywhere in arcengine's execution path), a lean recording's
  frames are always reconstructable later by replaying its action sequence
  against the same game locally. No replay tool exists yet; building one is
  a dependency of whichever future session builds the annotation viewer.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from .game_sources.base import FrameData

SCHEMA_VERSION = 2

RecordingMode = Literal["lean", "full"]


def _safe_component(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in value)


class Recorder:
    def __init__(self, recordings_dir: Path, source: str, game_id: str, mode: RecordingMode) -> None:
        self._recordings_dir = recordings_dir
        self._recordings_dir.mkdir(parents=True, exist_ok=True)
        self.mode = mode
        started_at = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        filename = (
            f"{_safe_component(source)}.{_safe_component(game_id)}."
            f"{mode}.{started_at}.recording.jsonl"
        )
        self.path = self._recordings_dir / filename
        self._step_index = 0

    def append(self, frame_data: FrameData) -> None:
        line = {
            "schema_version": SCHEMA_VERSION,
            "mode": self.mode,
            "step_index": self._step_index,
            "timestamp": datetime.now(UTC).isoformat(),
            "source": frame_data.source,
            "game_id": frame_data.game_id,
            "guid": frame_data.guid,
            "action_id": frame_data.action_input.id,
            "action_input": frame_data.action_input.data,
            "frame": frame_data.frame if self.mode == "full" else None,
            "state": str(frame_data.state),
            "levels_completed": frame_data.levels_completed,
            "win_levels": frame_data.win_levels,
            "available_actions": frame_data.available_actions,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            json.dump(line, f)
            f.write("\n")
        self._step_index += 1

    @property
    def step_count(self) -> int:
        return self._step_index


def recordings_dir_from_env() -> Path:
    return Path(os.environ.get("RECORDINGS_DIR", "recordings"))
