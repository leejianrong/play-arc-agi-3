"""FastAPI app: one WebSocket session endpoint plus the static frontend.

Each WebSocket connection owns one Arcade (ADR-0004) -- constructed once so
switching games mid-session doesn't re-fetch the catalog or open a new
scorecard -- plus a GameSource + Recorder pair, (re)created on the client's
"start" message. Errors are sent back as {"type": "error"} messages rather
than closing the connection, so a transient failure doesn't lose the session
or the recording (PLAN.md Q15).
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .annotations.session import AnnotationSession
from .config import api_key_from_env
from .game_sources.arcade import ArcadeGameSource, close_arcade, list_games, make_arcade
from .game_sources.base import FrameData, GameSourceError
from .recorder import Recorder, recordings_dir_from_env
from .stt.base import Transcriber
from .stt.endpoint import audio_endpoint
from .stt.whisper import WhisperTranscriber

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI()
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


_transcriber: Transcriber | None = None
_background_tasks: set[asyncio.Task] = set()
_transcriber_lock = asyncio.Lock()


async def get_transcriber() -> Transcriber:
    """One shared engine per process: loading a Whisper model is slow, so do it once."""
    global _transcriber
    async with _transcriber_lock:
        if _transcriber is None:
            candidate = WhisperTranscriber()
            await asyncio.to_thread(candidate.load)  # raises TranscriberUnavailable
            _transcriber = candidate
        return _transcriber


async def _warm_transcriber() -> None:
    try:
        await get_transcriber()
    except Exception:  # surfaced to the user when /ws/audio asks for it again
        pass


@app.websocket("/ws/audio")
async def audio(websocket: WebSocket) -> None:
    await audio_endpoint(websocket, lambda: get_transcriber())


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.websocket("/ws/session")
async def session(websocket: WebSocket) -> None:
    await websocket.accept()

    game_source: ArcadeGameSource | None = None
    recorder: Recorder | None = None
    annotation: AnnotationSession | None = None

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
                    annotate = bool(message.get("annotate"))
                    if annotate and record_mode == "off":
                        record_mode = "lean"  # ADR-0007: annotations need a recording to align to
                    if annotation is not None:
                        annotation.close()
                        annotation = None

                    game_source = ArcadeGameSource(arcade, game_id)
                    recorder = (
                        Recorder(recordings_dir_from_env(), "local", game_id, record_mode)
                        if record_mode != "off"
                        else None
                    )
                    if annotate and recorder is not None:
                        # Start loading the speech model now so it is warm by the time audio connects.
                        task = asyncio.create_task(_warm_transcriber())
                        _background_tasks.add(task)
                        task.add_done_callback(_background_tasks.discard)
                        annotation = AnnotationSession(
                            recorder.path,
                            game_id,
                            record_mode,
                            stt=os.environ.get("STT_MODEL", "small.en"),
                            keep_audio=os.environ.get("KEEP_AUDIO", "1") != "0",
                        )
                    frame_data = await game_source.reset()
                    if recorder is not None:
                        recorder.append(frame_data)
                    if annotation is not None:
                        annotation.mark_step(recorder.step_count - 1, frame_data.levels_completed)
                    await websocket.send_json({"type": "frame", "frame_data": frame_data.to_wire()})
                    if annotation is not None:
                        await websocket.send_json(
                            {
                                "type": "annotation",
                                "session_id": annotation.session_id,
                                "record": record_mode,
                            }
                        )

                elif msg_type == "action":
                    if game_source is None:
                        raise GameSourceError("no active session — send 'start' first")
                    frame_data: FrameData = await game_source.step(
                        message["action_id"], x=message.get("x"), y=message.get("y")
                    )
                    if recorder is not None:
                        recorder.append(frame_data)
                    if annotation is not None and recorder is not None:
                        annotation.mark_step(recorder.step_count - 1, frame_data.levels_completed)
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
        if annotation is not None:
            annotation.close()
        await close_arcade(arcade)
