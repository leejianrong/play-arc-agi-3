"""Custom (hand-authored) games live in `custom_games/` (tracked in git) and are copied into the
environments dir (`environment_files/`, a gitignored cache) at startup, so arc_agi's own scan finds them next
to the downloaded real games. See docs/CUSTOM-GAMES.md.

Copies, not symlinks: arc_agi's offline scan does not follow symlinked game folders.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

DEFAULT_SOURCE = Path(__file__).resolve().parent.parent / "custom_games"


def environments_dir_from_env() -> Path:
    return Path(os.environ.get("ARC_ENVIRONMENTS_DIR", "environment_files"))


def sync_custom_games(source: Path = DEFAULT_SOURCE, dest: Path | None = None) -> list[str]:
    """Copy every `<source>/<id>/` that has a metadata.json into `<dest>/<id>/`, only when it differs.

    Returns the ids that were added or updated. Nothing is ever deleted from `dest`.
    """
    dest = dest if dest is not None else environments_dir_from_env()
    changed: list[str] = []
    if not source.is_dir():
        return changed
    for game_dir in sorted(p for p in source.iterdir() if (p / "metadata.json").is_file()):
        target = dest / game_dir.name
        touched = False
        for file in sorted(f for f in game_dir.iterdir() if f.is_file() and f.suffix in {".py", ".json"}):
            out = target / file.name
            if out.is_file() and out.read_bytes() == file.read_bytes():
                continue
            target.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, out)
            touched = True
        if touched:
            changed.append(game_dir.name)
    return changed
