"""Data-use policy (ADR-0009): which games may be annotated, and how the data may be used.

`train-ok`        custom environments: usable for training.
`reference-only`  public ARC-AGI-3 games: human baseline only, excluded from training exports.
`heldout`         annotation refused, so the evaluation set stays free of human traces.

The assignment lives in data_policy.json, not code. A missing or malformed file refuses annotation
for every game (fail closed): quietly annotating a held-out game cannot be undone.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DataUse = Literal["train-ok", "reference-only", "heldout"]

DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "data_policy.json"


def base_id(game_id: str) -> str:
    """Catalog ids carry a version suffix (r11l-495a7899); the policy lists the part before it."""
    return game_id.split("-", 1)[0]


@dataclass(frozen=True, slots=True)
class Policy:
    public: frozenset[str]
    heldout: frozenset[str]
    error: str | None = None  # set when the file could not be trusted; everything is then refused

    def classify(self, game_id: str) -> DataUse:
        if self.error is not None:
            return "heldout"
        base = base_id(game_id)
        if base in self.heldout:
            return "heldout"
        if base in self.public:
            return "reference-only"
        return "train-ok"

    def refusal(self, game_id: str) -> str:
        if self.error is not None:
            return f"annotation refused: data policy unusable ({self.error})"
        return (
            f"annotation refused: {game_id} is a held-out game (data_policy.json). "
            "You can still play it without annotating."
        )


def load_policy(path: Path | None = None) -> Policy:
    path = path or Path(os.environ.get("DATA_POLICY", DEFAULT_PATH))
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        public = frozenset(str(x) for x in raw["public"])
        heldout = frozenset(str(x) for x in raw["heldout"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return Policy(frozenset(), frozenset(), error=f"{path.name}: {type(exc).__name__}: {exc}")
    return Policy(public, heldout)
