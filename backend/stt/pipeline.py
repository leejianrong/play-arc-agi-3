"""Audio pipeline (ADR-0006): PCM16 stream -> utterances -> interim and final text.

Transcription is blocking CPU work, so it runs in a worker thread, one job at a time. Interims
(a re-transcription of the still-open utterance) are best-effort and skipped while the engine is
busy or a final is queued; finals are queued and never dropped. Interim cadence is measured in
*audio* time, not wall time, so behaviour is deterministic in tests and independent of how fast
the engine runs.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .base import SAMPLE_RATE, Transcriber, clean_text
from .segmenter import SegmenterConfig, UtteranceDiscarded, UtteranceEnd, UtteranceSegmenter, UtteranceStart


@dataclass(frozen=True, slots=True)
class Utterance:
    utterance_id: int
    text: str
    start_sample: int
    end_sample: int


class AudioPipeline:
    def __init__(
        self,
        transcriber: Transcriber,
        on_interim: Callable[[int, str], Awaitable[None]],
        on_final: Callable[[Utterance], Awaitable[None]],
        on_discard: Callable[[int], Awaitable[None]] | None = None,
        on_error: Callable[[str], Awaitable[None]] | None = None,
        interim_every_ms: int = 1500,
        segmenter_config: SegmenterConfig | None = None,
    ) -> None:
        self._transcriber = transcriber
        self._on_interim = on_interim
        self._on_final = on_final
        self._on_discard = on_discard
        self._on_error = on_error
        self._interim_every_samples = SAMPLE_RATE * interim_every_ms // 1000
        self._segmenter = UtteranceSegmenter(segmenter_config)
        self._lock = asyncio.Lock()  # one transcription at a time
        self._finals: asyncio.Queue[Utterance | None] = asyncio.Queue()
        self._worker = asyncio.create_task(self._final_worker())
        self._utterance_id = 0
        self._last_interim_sample = 0
        self._interim_task: asyncio.Task | None = None
        self._pending_finals = 0

    @property
    def samples_consumed(self) -> int:
        return self._segmenter.samples_consumed

    async def feed(self, pcm: bytes) -> None:
        for event in self._segmenter.feed(pcm):
            await self._handle(event)
        self._maybe_start_interim()

    async def flush(self) -> None:
        """Close the open utterance now (e.g. on mute) without shutting the pipeline down."""
        for event in self._segmenter.flush():
            await self._handle(event)

    async def aclose(self) -> None:
        """Flush the open utterance, finish queued finals, stop the worker."""
        for event in self._segmenter.flush():
            await self._handle(event)
        if self._interim_task is not None:
            self._interim_task.cancel()
        await self._finals.put(None)
        await self._worker

    async def _handle(self, event) -> None:
        if isinstance(event, UtteranceStart):
            self._utterance_id += 1
            self._last_interim_sample = event.start_sample
        elif isinstance(event, UtteranceEnd):
            if self._interim_task is not None:
                self._interim_task.cancel()
            self._pending_finals += 1
            await self._finals.put((self._utterance_id, event))
        elif isinstance(event, UtteranceDiscarded) and self._on_discard is not None:
            await self._on_discard(self._utterance_id)

    def _maybe_start_interim(self) -> None:
        if not self._segmenter.is_open or self._pending_finals or self._lock.locked():
            return
        if self._interim_task is not None and not self._interim_task.done():
            return
        now = self._segmenter.samples_consumed
        if now - self._last_interim_sample < self._interim_every_samples:
            return
        self._last_interim_sample = now
        self._interim_task = asyncio.create_task(
            self._interim(self._utterance_id, self._segmenter.open_pcm())
        )

    async def _transcribe(self, pcm: bytes) -> str:
        async with self._lock:
            return clean_text(await asyncio.to_thread(self._transcriber.transcribe, pcm))

    async def _interim(self, utterance_id: int, pcm: bytes) -> None:
        try:
            text = await self._transcribe(pcm)
        except Exception as exc:  # an engine failure must not kill the audio loop
            await self._report(exc)
            return
        # Drop it if the utterance already closed (the final will supersede it).
        if text and self._segmenter.is_open and utterance_id == self._utterance_id:
            await self._on_interim(utterance_id, text)

    async def _final_worker(self) -> None:
        while True:
            item = await self._finals.get()
            if item is None:
                return
            utterance_id, event = item
            try:
                text = await self._transcribe(event.pcm)
                if text:
                    await self._on_final(
                        Utterance(utterance_id, text, event.start_sample, event.end_sample)
                    )
                elif self._on_discard is not None:
                    await self._on_discard(utterance_id)
            except Exception as exc:
                await self._report(exc)
            finally:
                self._pending_finals -= 1

    async def _report(self, exc: Exception) -> None:
        if self._on_error is not None:
            await self._on_error(f"transcription failed: {exc}")
