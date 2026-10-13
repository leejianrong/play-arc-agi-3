"""Synthetic PCM16 mono 16 kHz audio for STT tests: speech-like tone, silence, key clicks."""

import math
import random
from array import array

SAMPLE_RATE = 16_000


def _pcm(samples) -> bytes:
    return array("h", samples).tobytes()


def tone(ms: int, amplitude: int = 4000, hz: int = 180) -> bytes:
    n = SAMPLE_RATE * ms // 1000
    return _pcm(int(amplitude * math.sin(2 * math.pi * hz * i / SAMPLE_RATE)) for i in range(n))


def silence(ms: int, noise: int = 15, seed: int = 1) -> bytes:
    rng = random.Random(seed)
    n = SAMPLE_RATE * ms // 1000
    return _pcm(rng.randint(-noise, noise) for _ in range(n))


def click(ms: int = 40, amplitude: int = 9000) -> bytes:
    """A key-press transient: loud but far shorter than a spoken word."""
    return tone(ms, amplitude=amplitude, hz=2500)


def speechlike(ms: int) -> bytes:
    """Words separated by brief gaps. Real speech always has them; an unbroken tone is
    (correctly) treated by the segmenter as steady background once its noise floor adapts."""
    unit = tone(400) + silence(100)
    reps = max(1, ms // 500)
    return unit * reps
