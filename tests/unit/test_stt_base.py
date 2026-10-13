import pytest

from backend.stt.base import FakeTranscriber, TranscriberUnavailable, clean_text


@pytest.mark.parametrize(
    "raw", ["", "  ", "you", "Thank you.", "Thanks for watching!", "[BLANK_AUDIO]", "..."]
)
def test_clean_text_drops_whisper_silence_hallucinations(raw):
    assert clean_text(raw) == ""


def test_clean_text_normalizes_whitespace_and_keeps_real_speech():
    assert clean_text("  the blue \n square   moves ") == "the blue square moves"
    assert clean_text("Thank you for the hint, it moves left") == "Thank you for the hint, it moves left"


def test_fake_transcriber_scripts_and_records_calls():
    fake = FakeTranscriber(["one", "two"])
    fake.load()
    assert [fake.transcribe(b"\0\0" * 16000), fake.transcribe(b"\0\0"), fake.transcribe(b"\0\0")] == [
        "one",
        "two",
        "two",
    ]
    assert fake.calls == [32000, 2, 2]


def test_fake_transcriber_can_simulate_unavailable_engine():
    with pytest.raises(TranscriberUnavailable):
        FakeTranscriber(load_error="no model").load()


@pytest.mark.parametrize("raw", ["Um...", "umm", "Uh,", "Hmm.", "mm-hmm", "Ahh", "er", "Erm..."])
def test_clean_text_drops_lone_hesitations(raw):
    assert clean_text(raw) == ""


def test_clean_text_keeps_real_sentences_that_start_with_a_filler():
    assert clean_text("Um, I think the cross rotates it") == "Um, I think the cross rotates it"
    assert clean_text("Okay") == "Okay"
