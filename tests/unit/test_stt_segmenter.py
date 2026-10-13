from backend.stt.segmenter import (
    SegmenterConfig,
    UtteranceDiscarded,
    UtteranceEnd,
    UtteranceSegmenter,
    UtteranceStart,
)
from tests.helpers.audio import SAMPLE_RATE, click, silence, tone


def run(*chunks: bytes, config: SegmenterConfig | None = None):
    seg = UtteranceSegmenter(config)
    events = []
    for chunk in chunks:
        events.extend(seg.feed(chunk))
    return seg, events


def test_speech_between_silence_yields_start_then_end_with_boundaries():
    _, events = run(silence(500), tone(1000), silence(1000))
    kinds = [type(e) for e in events]
    assert kinds == [UtteranceStart, UtteranceEnd]
    start, end = events
    assert abs(start.start_sample - 0.5 * SAMPLE_RATE) <= 0.03 * SAMPLE_RATE
    assert abs(end.end_sample - 1.5 * SAMPLE_RATE) <= 0.06 * SAMPLE_RATE
    assert len(end.pcm) > 1.0 * SAMPLE_RATE * 2  # speech plus pre-roll


def test_short_pause_inside_speech_does_not_split_the_utterance():
    _, events = run(tone(600), silence(300), tone(600), silence(1000))
    assert [type(e) for e in events] == [UtteranceStart, UtteranceEnd]


def test_long_pause_splits_into_two_utterances():
    _, events = run(tone(600), silence(1000), tone(600), silence(1000))
    assert [type(e) for e in events] == [UtteranceStart, UtteranceEnd, UtteranceStart, UtteranceEnd]


def test_key_clatter_never_opens_an_utterance():
    _, events = run(silence(300), click(), silence(400), click(), silence(400), click(), silence(600))
    assert events == []


def test_loud_burst_just_over_start_threshold_but_under_min_speech_is_discarded():
    _, events = run(silence(300), tone(120), silence(1000))
    assert [type(e) for e in events] == [UtteranceStart, UtteranceDiscarded]


def test_chunk_boundaries_do_not_matter():
    audio = silence(400) + tone(900) + silence(900)
    whole = run(audio)[1]
    odd = UtteranceSegmenter()
    events = []
    for i in range(0, len(audio), 777):  # not a multiple of the frame size
        events.extend(odd.feed(audio[i : i + 777]))
    assert [(type(e), getattr(e, "start_sample", None)) for e in events] == [
        (type(e), getattr(e, "start_sample", None)) for e in whole
    ]


def test_max_utterance_length_forces_a_cut():
    config = SegmenterConfig(max_utterance_ms=2000)
    # Speech-like: words with brief gaps (a pure unbroken tone would, correctly, read as hiss).
    words = (tone(400) + silence(100)) * 10
    _, events = run(words, silence(1000), config=config)
    assert sum(isinstance(e, UtteranceEnd) for e in events) >= 2


def test_flush_closes_an_open_utterance_and_ignores_idle():
    seg = UtteranceSegmenter()
    seg.feed(silence(200) + tone(800))
    assert seg.is_open
    assert [type(e) for e in seg.flush()] == [UtteranceEnd]
    assert UtteranceSegmenter().flush() == []


def test_steady_hiss_above_the_absolute_floor_stops_counting_as_speech():
    # RMS ~400 beats the 250 absolute floor, so the first second may open an utterance, but once
    # the rolling noise floor has adapted it must close and stay quiet rather than run forever.
    seg, events = run(silence(6000, noise=700))
    assert not seg.is_open
    assert sum(isinstance(e, UtteranceStart) for e in events) <= 1


def test_speech_over_steady_hiss_is_still_detected_after_warmup():
    _, events = run(silence(3000, noise=700), tone(1000, amplitude=5000), silence(1500, noise=700))
    assert [type(e) for e in events][-2:] == [UtteranceStart, UtteranceEnd]


def test_speech_at_the_very_start_of_the_stream_is_not_swallowed_by_warmup():
    _, events = run(tone(800), silence(1000))
    assert [type(e) for e in events] == [UtteranceStart, UtteranceEnd]
