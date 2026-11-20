"""Word timing: aligning the script's words to Whisper's timed words (pipeline/word_align.py)."""

import pytest

from pipeline.word_align import HeardWord, align_segment_words, snap_to_speech


def H(*items):
    return [HeardWord(w, s, e) for w, s, e in items]


def test_digits_and_spelling_quirks_still_align():
    # script writes "25 किलो DAP" style digits and ज़; Whisper writes number words and ज
    heard = H(("पच्चीस", 0.10, 0.60), ("किलो", 0.62, 0.95), ("खाद", 1.00, 1.30), ("ज़रूरी", 1.40, 1.80), ("है", 1.82, 2.00))
    words, ratios = align_segment_words(["25 किलो खाद जरूरी है।"], [(0.1, 2.0)], heard)
    assert [w.text for w in words] == ["25", "किलो", "खाद", "जरूरी", "है।"]
    assert all(w.timed for w in words) and ratios[0] > 0.9
    assert words[0].start == pytest.approx(0.10) and words[0].end == pytest.approx(0.60)
    assert words[3].start == pytest.approx(1.40)


def test_missing_word_is_filled_between_neighbours():
    heard = H(("मिट्टी", 0.0, 0.5), ("जांच", 1.1, 1.5), ("कराएं", 1.5, 2.0))  # "की" not heard
    words, _ = align_segment_words(["मिट्टी की जांच कराएं।"], [(0.0, 2.0)], heard)
    ki = words[1]
    assert not ki.timed and 0.5 <= ki.start < ki.end <= 1.1


def test_words_stay_inside_their_segment_span():
    # Whisper lets the last word run into the pause; the span (known from assembly) bounds it
    heard = H(("नमूना", 0.0, 0.5), ("लें", 0.5, 1.4), ("फिर", 1.6, 1.9), ("सुखाएं", 1.9, 2.4))
    words, _ = align_segment_words(["नमूना लें।", "फिर सुखाएं।"], [(0.0, 0.9), (1.6, 2.4)], heard)
    assert words[1].end == pytest.approx(0.9)
    assert [w.segment for w in words] == [0, 0, 1, 1]


def test_weak_segment_falls_back_to_proportional():
    heard = H(("कुछ", 0.0, 0.5), ("और", 0.5, 1.0))  # nothing like the script
    words, ratios = align_segment_words(["मिट्टी की जांच कराएं।"], [(0.0, 2.0)], heard)
    assert ratios[0] < 0.6 and not any(w.timed for w in words)
    assert words[0].start == 0.0 and words[-1].end == pytest.approx(2.0)


def test_snap_moves_starts_out_of_silence():
    heard = H(("हटाएं,", 1.74, 2.16), ("और", 2.24, 2.72), ("फावड़े", 2.72, 3.32))
    snapped = snap_to_speech(heard, [(2.14, 2.52)])
    assert snapped[0].end == pytest.approx(2.14)     # end that ran into the pause pulled back
    assert snapped[1].start == pytest.approx(2.52)   # start inside the pause moved to speech onset
    assert snapped[2].start == pytest.approx(2.72)
    # a start just before a silence (within tolerance) also moves; one well before does not
    assert snap_to_speech(H(("जैसे", 11.44, 12.02)), [(11.49, 11.71)])[0].start == pytest.approx(11.71)
    assert snap_to_speech(H(("इस", 3.70, 4.52)), [(3.87, 4.12)])[0].start == pytest.approx(3.70)
