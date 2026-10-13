"""The /ws/audio route (ADR-0006).

Wire protocol, client -> server:
  text   {"type": "audio_start"}   marks stream time zero (sent once, when capture begins)
  binary 0x01 + PCM16LE mono 16 kHz   audio for transcription
  binary 0x02 + opus/webm chunk       raw audio for retention (written verbatim)
Server -> client (JSON): status, interim, final, discard, error.

Audio retention works even when transcription is unavailable, so a missing model never loses the
session's audio or blocks play (PLAN Q34).
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable

from fastapi import WebSocket, WebSocketDisconnect

from ..annotations.session import AnnotationSession, get_session
from .base import SAMPLE_RATE, Transcriber, TranscriberUnavailable
from .pipeline import AudioPipeline, Utterance
from .segmenter import SegmenterConfig

log = logging.getLogger(__name__)

TAG_PCM = 0x01
TAG_OPUS = 0x02

GetTranscriber = Callable[[], Awaitable[Transcriber]]


async def audio_endpoint(websocket: WebSocket, get_transcriber: GetTranscriber) -> None:
    await websocket.accept()
    send_lock = asyncio.Lock()

    async def send(message: dict) -> None:
        # The client may be gone while a queued final is still being written; the sidecar write
        # happens before the send, so a failed send loses only the UI echo.
        try:
            async with send_lock:
                await websocket.send_json(message)
        except Exception:
            log.debug("audio websocket send failed", exc_info=True)

    session = get_session(websocket.query_params.get("session", ""))
    if session is None:
        await send({"type": "error", "code": "no_session", "message": "no active annotated session"})
        await websocket.close()
        return

    pipeline: AudioPipeline | None = None
    audio_t0_ms = session.now_ms()

    def ms(sample: int) -> int:
        return audio_t0_ms + sample * 1000 // SAMPLE_RATE

    async def on_interim(utterance_id: int, text: str) -> None:
        await send({"type": "interim", "utterance_id": utterance_id, "text": text})

    async def on_final(u: Utterance) -> None:
        event = _record_speech(session, u, ms)
        await send(
            {
                "type": "final",
                "utterance_id": u.utterance_id,
                "text": u.text,
                "event_id": event["event_id"],
                "step_at_start": event["step_at_start"],
                "step_at_end": event["step_at_end"],
            }
        )

    async def on_discard(utterance_id: int) -> None:
        await send({"type": "discard", "utterance_id": utterance_id})

    async def on_error(message: str) -> None:
        await send({"type": "error", "code": "stt_failed", "message": message})

    try:
        await send({"type": "status", "state": "loading"})
        try:
            transcriber = await get_transcriber()
            pipeline = AudioPipeline(
                transcriber,
                on_interim,
                on_final,
                on_discard=on_discard,
                on_error=on_error,
                segmenter_config=SegmenterConfig(
                    # Longer = fewer mid-sentence splits and better Whisper context, but a later final.
                    silence_ms=int(os.environ.get("STT_SILENCE_MS", "1000")),
                ),
            )
            await send({"type": "status", "state": "ready", "engine": transcriber.name})
        except TranscriberUnavailable as exc:
            await send({"type": "error", "code": "stt_unavailable", "message": str(exc)})

        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("text") is not None:
                if '"audio_start"' in message["text"]:
                    audio_t0_ms = session.now_ms()
                continue
            data = message.get("bytes")
            if not data:
                continue
            if data[0] == TAG_PCM and pipeline is not None:
                await pipeline.feed(data[1:])
            elif data[0] == TAG_OPUS:
                session.write_audio(data[1:])
    except WebSocketDisconnect:
        pass
    finally:
        if pipeline is not None:
            try:
                await pipeline.aclose()
            except Exception:  # the socket is gone; the sidecar already has what was final
                log.exception("audio pipeline shutdown failed")


def _record_speech(session: AnnotationSession, u: Utterance, ms: Callable[[int], int]) -> dict:
    start_ms, end_ms = ms(u.start_sample), ms(u.end_sample)
    offset = (u.start_sample * 1000 // SAMPLE_RATE, u.end_sample * 1000 // SAMPLE_RATE)
    return session.speech(u.text, start_ms, end_ms, offset)
