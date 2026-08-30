from __future__ import annotations

import os

from .game_sources.base import GameSourceError


def api_key_from_env() -> str:
    key = os.environ.get("ARC_API_KEY")
    if not key:
        raise GameSourceError(
            "ARC_API_KEY is not set. Get a key from https://arcprize.org/platform and set it in .env."
        )
    return key
