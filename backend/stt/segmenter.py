"""Energy-based utterance segmenter (ADR-0006): cuts a continuous PCM16 stream into utterances.

Pure Python and dependency-free so it is testable in CI. It only decides *where* speech starts and
ends; Whisper (with its own VAD filter) decides *what* was said, so a missed boundary costs little.

Keyboard clatter is the main false-positive source: a key press is a transient well under
`start_ms` of sustained energy, so it never opens an utterance, and anything that does open but
holds under `min_speech_ms` of loud frames is discarded.
"""

from __future__ import annotations

import math
from array import array
from collections import deque
from dataclasses import dataclass

from .base import BYTES_PER_SAMPLE, SAMPLE_RATE


@dataclass(frozen=True, slots=True)
class SegmenterConfig:
    frame_ms: int = 30
    start_ms: int = 90  # sustained loud audio needed to open an utterance
    silence_ms: int = 700  # quiet needed to close one
    preroll_ms: int = 300  # audio kept from before onset so words aren't clipped
    min_speech_ms: int = 250  # loud time below which an utterance is discarded as noise
    max_utterance_ms: int = 30_000  # force a cut (Whisper works on <= 30 s windows)
    min_threshold: float = 250.0  # absolute RMS floor (int16 scale, about -42 dBFS)
    noise_multiplier: float = 3.0  # threshold = max(min_threshold, noise_floor * this)
    noise_window_ms: int = 10_000  # recent audio the noise floor is estimated from
    noise_percentile: float = 0.10  # low percentile of recent frame levels = the background
    noise_warmup_ms: int = 1_000  # before this much audio, trust only min_threshold


@dataclass(frozen=True, slots=True)
class UtteranceStart:
    start_sample: int  # onset of speech, in samples since the stream began


@dataclass(frozen=True, slots=True)
class UtteranceEnd:
    start_sample: int  # onset of speech
    end_sample: int  # end of the last loud frame
    pcm: bytes  # audio including pre-roll and trailing quiet


@dataclass(frozen=True, slots=True)
class UtteranceDiscarded:
    start_sample: int


SegEvent = UtteranceStart | UtteranceEnd | UtteranceDiscarded


def frame_rms(frame: bytes) -> float:
    samples = array("h")
    samples.frombytes(frame)
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


class UtteranceSegmenter:
    def __init__(self, config: SegmenterConfig | None = None) -> None:
        self.config = config or SegmenterConfig()
        c = self.config
        self._frame_samples = SAMPLE_RATE * c.frame_ms // 1000
        self._frame_bytes = self._frame_samples * BYTES_PER_SAMPLE
        self._start_frames = max(1, c.start_ms // c.frame_ms)
        self._silence_frames = max(1, c.silence_ms // c.frame_ms)
        self._max_frames = c.max_utterance_ms // c.frame_ms
        self._levels: deque[float] = deque(maxlen=max(1, c.noise_window_ms // c.frame_ms))
        self._warmup_frames = c.noise_warmup_ms // c.frame_ms
        self._noise_floor = c.min_threshold / c.noise_multiplier
        self._pending = b""
        self._next_frame_index = 0  # frames consumed so far
        self._preroll: deque[tuple[int, bytes]] = deque(maxlen=max(1, c.preroll_ms // c.frame_ms))
        self._run: list[tuple[int, bytes]] = []  # consecutive loud frames not yet an utterance
        self._open = False
        self._frames: list[bytes] = []
        self._onset_frame = 0
        self._last_loud_frame = 0
        self._loud_frames = 0
        self._silent_run = 0

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def threshold(self) -> float:
        return max(self.config.min_threshold, self._noise_floor * self.config.noise_multiplier)

    @property
    def samples_consumed(self) -> int:
        return self._next_frame_index * self._frame_samples

    def open_pcm(self) -> bytes:
        """Audio of the currently open utterance so far (for interim transcription)."""
        return b"".join(self._frames)

    def open_start_sample(self) -> int:
        return self._onset_frame * self._frame_samples

    def feed(self, pcm: bytes) -> list[SegEvent]:
        data = self._pending + pcm
        events: list[SegEvent] = []
        usable = len(data) - len(data) % self._frame_bytes
        for offset in range(0, usable, self._frame_bytes):
            events.extend(self._on_frame(data[offset : offset + self._frame_bytes]))
        self._pending = data[usable:]
        return events

    def flush(self) -> list[SegEvent]:
        """End of stream: close an open utterance so the last words aren't lost."""
        if not self._open:
            return []
        return [self._close()]

    def _on_frame(self, frame: bytes) -> list[SegEvent]:
        index = self._next_frame_index
        self._next_frame_index += 1
        level = frame_rms(frame)
        self._track_noise(index, level)
        loud = level > self.threshold

        if not self._open:
            if not loud:
                self._run.clear()
                self._preroll.append((index, frame))
                return []
            self._run.append((index, frame))
            if len(self._run) < self._start_frames:
                return []
            self._open = True
            self._onset_frame = self._run[0][0]
            lead = [f for i, f in self._preroll if i < self._onset_frame]
            self._frames = lead + [f for _, f in self._run]
            self._loud_frames = len(self._run)
            self._last_loud_frame = index
            self._silent_run = 0
            self._run.clear()
            self._preroll.clear()
            return [UtteranceStart(self._onset_frame * self._frame_samples)]

        self._frames.append(frame)
        if loud:
            self._loud_frames += 1
            self._last_loud_frame = index
            self._silent_run = 0
        else:
            self._silent_run += 1
        too_long = len(self._frames) >= self._max_frames
        if self._silent_run >= self._silence_frames or too_long:
            return [self._close()]
        return []

    def _track_noise(self, index: int, level: float) -> None:
        """Rolling low percentile of recent levels: steady hiss raises the bar, speech (which has
        gaps between words) barely moves a low percentile, so it can't lift its own threshold."""
        self._levels.append(level)
        if index < self._warmup_frames or index % 5:
            return
        ranked = sorted(self._levels)
        self._noise_floor = ranked[int(len(ranked) * self.config.noise_percentile)]

    def _close(self) -> SegEvent:
        c = self.config
        start_sample = self._onset_frame * self._frame_samples
        loud_ms = self._loud_frames * c.frame_ms
        pcm = b"".join(self._frames)
        end_sample = (self._last_loud_frame + 1) * self._frame_samples
        self._open = False
        self._frames = []
        self._silent_run = 0
        self._loud_frames = 0
        if loud_ms < c.min_speech_ms:
            return UtteranceDiscarded(start_sample)
        return UtteranceEnd(start_sample, end_sample, pcm)
