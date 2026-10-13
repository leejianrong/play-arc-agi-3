"""The Transcriber contract (ADR-0006): PCM16 mono 16 kHz bytes in, text out.

Kept free of numpy/faster-whisper so the base install, `make check` and CI
never need the optional `stt` extra. Tests use FakeTranscriber.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Protocol

SAMPLE_RATE = 16_000
BYTES_PER_SAMPLE = 2


class TranscriberUnavailable(RuntimeError):
    """The engine can't run here (extra not installed, model failed to load)."""


class Transcriber(Protocol):
    name: str

    def load(self) -> None:
        """Load the model. Blocking; called from a worker thread. Raises TranscriberUnavailable."""

    def transcribe(self, pcm16: bytes) -> str:
        """Transcribe one utterance's audio. Blocking; called from a worker thread."""


class FakeTranscriber:
    """Deterministic stand-in: returns scripted texts in order, else a description of the audio."""

    def __init__(self, texts: list[str] | None = None, load_error: str | None = None) -> None:
        self.name = "fake"
        self._texts = list(texts or [])
        self._load_error = load_error
        self.calls: list[int] = []

    def load(self) -> None:
        if self._load_error:
            raise TranscriberUnavailable(self._load_error)

    def transcribe(self, pcm16: bytes) -> str:
        self.calls.append(len(pcm16))
        if self._texts:
            return self._texts[min(len(self.calls) - 1, len(self._texts) - 1)]
        return f"heard {len(pcm16) / (SAMPLE_RATE * BYTES_PER_SAMPLE):.1f}s of audio"


TranscriberFactory = Callable[[], Transcriber]

# Whisper hallucinates these on silence/noise; they are never real think-aloud.
_PHANTOMS = {
    "you",
    "thank you",
    "thanks for watching",
    "thank you for watching",
    "bye",
    "[blank_audio]",
    "[silence]",
    "[music]",
    "(silence)",
}


# A segment that is only a hesitation noise carries no reasoning ("Um...", "Umm", "hmm").
_FILLER = re.compile(r"^(?:u+m+|u+h+|h+m+|m+h*m+|e+r+m*|a+h+)$")


def clean_text(text: str) -> str:
    """Normalize whitespace; drop Whisper silence hallucinations and lone hesitations ('' if nothing)."""
    text = re.sub(r"\s+", " ", text).strip()
    bare = re.sub(r"[^\w\[\]() ]", "", text).strip().lower()
    if not bare or bare in _PHANTOMS or _FILLER.match(bare):
        return ""
    return text
