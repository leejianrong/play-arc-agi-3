"""faster-whisper engine (ADR-0006). Needs the optional `stt` extra."""

from __future__ import annotations

import os

from .base import TranscriberUnavailable, clean_text

DEFAULT_MODEL = "small.en"


class WhisperTranscriber:
    def __init__(
        self,
        model: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
    ) -> None:
        self.model_name = model or os.environ.get("STT_MODEL", DEFAULT_MODEL)
        self._device = device or os.environ.get("STT_DEVICE", "auto")
        self._compute_type = compute_type or os.environ.get("STT_COMPUTE_TYPE", "default")
        self.name = f"faster-whisper:{self.model_name}"
        self._model = None

    def load(self) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise TranscriberUnavailable(
                "faster-whisper is not installed; run `make run-annotate` (uv sync --extra stt)"
            ) from exc
        try:
            self._model = WhisperModel(
                self.model_name,
                device=self._device,
                compute_type="int8" if self._compute_type == "default" and self._device != "cuda"
                else self._compute_type,
                cpu_threads=int(os.environ.get("STT_CPU_THREADS", "8")),
            )
        except Exception as exc:  # download/offline/corrupt cache/CUDA problems
            raise TranscriberUnavailable(f"could not load Whisper model {self.model_name!r}: {exc}") from exc

    def transcribe(self, pcm16: bytes) -> str:
        import numpy as np

        if self._model is None:
            raise TranscriberUnavailable("model not loaded")
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _info = self._model.transcribe(
            audio,
            language="en",
            beam_size=1,
            temperature=0.0,  # no fallback re-decodes: they cost seconds on a cut-off interim
            condition_on_previous_text=False,
            vad_filter=True,
            no_speech_threshold=0.6,
        )
        parts = [s.text for s in segments if s.no_speech_prob < 0.6 and s.avg_logprob > -1.2]
        return clean_text(" ".join(parts))
