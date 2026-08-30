"""One-off bulk download: fetch every real game's source into environment_files/.

Idempotent -- arc_agi skips the network call for a game already cached on
disk (arc_agi/base.py's _download_game checks for the source file first),
so re-running this later (e.g. after ARC adds new games) only downloads
what's new.
"""

import sys
import time

from dotenv import load_dotenv

from backend.config import api_key_from_env
from backend.game_sources.base import GameSourceError


def main() -> None:
    load_dotenv()

    from arc_agi import Arcade, OperationMode

    try:
        api_key = api_key_from_env()
    except GameSourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    arcade = Arcade(arc_api_key=api_key, operation_mode=OperationMode.NORMAL)
    games = sorted(arcade.available_environments, key=lambda e: e.game_id)
    print(f"{len(games)} games in the catalog\n")

    ok, failed = 0, []
    for env in games:
        already_cached = env.local_dir is not None
        t0 = time.time()
        wrapper = arcade.make(env.game_id)
        elapsed = time.time() - t0
        if wrapper is None:
            failed.append(env.game_id)
            print(f"  FAILED  {env.game_id}")
            continue
        ok += 1
        tag = "cached" if already_cached else f"downloaded in {elapsed:.1f}s"
        print(f"  ok      {env.game_id:<20} {tag}")

    arcade.close_scorecard()

    print(f"\n{ok}/{len(games)} games available locally under environment_files/")
    if failed:
        print(f"failed: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
