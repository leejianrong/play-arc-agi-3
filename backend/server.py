"""FastAPI app: one WebSocket session endpoint plus the static frontend.

Each WebSocket connection owns its own RemoteGameSource + Recorder, created
lazily on the client's "start" message. Errors are sent back as {"type":
"error"} messages rather than closing the connection, so a transient API
failure doesn't lose the session or the recording (PLAN.md Q15).
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .game_sources.base import FrameData, GameSource, GameSourceError
from .game_sources.remote import RemoteGameSource, api_key_from_env, list_remote_games
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

    game_source: Optional[GameSource] = None
    recorder: Optional[Recorder] = None

    try:
        api_key = api_key_from_env()
    except GameSourceError as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close()
        return

    try:
        games = await list_remote_games(api_key)
        await websocket.send_json(
            {"type": "games", "games": [asdict(g) for g in games]}
        )
    except GameSourceError as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})

    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")

            try:
                if msg_type == "start":
                    game_id = message["game_id"]
                    if game_source is not None:
                        await game_source.close()
                    game_source = RemoteGameSource(game_id, api_key)
                    recorder = Recorder(recordings_dir_from_env(), "remote", game_id)
                    frame_data = await game_source.reset()
                    recorder.append(frame_data)
                    await websocket.send_json({"type": "frame", "frame_data": frame_data.to_wire()})

                elif msg_type == "action":
                    if game_source is None or recorder is None:
                        raise GameSourceError("no active session — send 'start' first")
                    frame_data: FrameData = await game_source.step(
                        message["action_id"], x=message.get("x"), y=message.get("y")
                    )
                    recorder.append(frame_data)
                    await websocket.send_json({"type": "frame", "frame_data": frame_data.to_wire()})

                else:
                    await websocket.send_json({"type": "error", "message": f"unknown message type {msg_type!r}"})

            except GameSourceError as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})

    except WebSocketDisconnect:
        pass
    finally:
        if game_source is not None:
            await game_source.close()
