"""FastAPI app: one WebSocket session endpoint plus the static frontend.

Each WebSocket connection owns one Arcade (ADR-0004) -- constructed once so
switching games mid-session doesn't re-fetch the catalog or open a new
scorecard -- plus a GameSource + Recorder pair, (re)created on the client's
"start" message. Errors are sent back as {"type": "error"} messages rather
than closing the connection, so a transient failure doesn't lose the session
or the recording (PLAN.md Q15).
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import api_key_from_env
from .game_sources.arcade import ArcadeGameSource, close_arcade, list_games, make_arcade
from .game_sources.base import FrameData, GameSourceError
from .recorder import Recorder, recordings_dir_from_env

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI()
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.websocket("/ws/session")
async def session(websocket: WebSocket) -> None:
    await websocket.accept()

    game_source: ArcadeGameSource | None = None
    recorder: Recorder | None = None

    try:
        api_key = api_key_from_env()
    except GameSourceError as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close()
        return

    try:
        arcade = await make_arcade(api_key)
        await websocket.send_json(
            {"type": "games", "games": [asdict(g) for g in list_games(arcade)]}
        )
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": f"failed to load games catalog: {exc}"})
        await websocket.close()
        return

    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")

            try:
                if msg_type == "start":
                    game_id = message["game_id"]
                    record_mode = message.get("record", "off")
                    if record_mode not in ("off", "lean", "full"):
                        raise GameSourceError(f"unknown record mode {record_mode!r}")

                    game_source = ArcadeGameSource(arcade, game_id)
                    recorder = (
                        Recorder(recordings_dir_from_env(), "local", game_id, record_mode)
                        if record_mode != "off"
                        else None
                    )
                    frame_data = await game_source.reset()
                    if recorder is not None:
                        recorder.append(frame_data)
                    await websocket.send_json({"type": "frame", "frame_data": frame_data.to_wire()})

                elif msg_type == "action":
                    if game_source is None:
                        raise GameSourceError("no active session — send 'start' first")
                    frame_data: FrameData = await game_source.step(
                        message["action_id"], x=message.get("x"), y=message.get("y")
                    )
                    if recorder is not None:
                        recorder.append(frame_data)
                    await websocket.send_json({"type": "frame", "frame_data": frame_data.to_wire()})

                else:
                    await websocket.send_json(
                        {"type": "error", "message": f"unknown message type {msg_type!r}"}
                    )

            except GameSourceError as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})

    except WebSocketDisconnect:
        pass
    finally:
        await close_arcade(arcade)
