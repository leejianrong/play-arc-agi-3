import os
import socket
import sys

import uvicorn
from dotenv import load_dotenv

HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def resolve_port(preferred: int, host: str) -> int:
    """Bind the preferred port if free; otherwise let the OS assign a free one.

    Local dev machines routinely have something else already on 8000 (this
    one has a Docker-proxied service there) — refusing to start over a port
    clash would be a needless failure for a single-user local tool.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, preferred))
            return preferred
        except OSError:
            probe.bind((host, 0))
            return probe.getsockname()[1]


def main() -> None:
    load_dotenv()

    from backend.custom_games import sync_custom_games

    updated = sync_custom_games()
    if updated:
        print(f"custom games synced into the environments dir: {', '.join(updated)}")

    from backend.config import api_key_from_env
    from backend.game_sources.base import GameSourceError

    try:
        api_key_from_env()
    except GameSourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    preferred_port = int(os.environ.get("PORT", DEFAULT_PORT))
    port = resolve_port(preferred_port, HOST)
    if port != preferred_port:
        print(f"port {preferred_port} is in use, using {port} instead", file=sys.stderr)

    url = f"http://{HOST}:{port}"
    print(f"\n  ARC Play running at {url}\n  (not opened automatically -- open it yourself)\n")
    uvicorn.run("backend.server:app", host=HOST, port=port, reload=False)


if __name__ == "__main__":
    main()
