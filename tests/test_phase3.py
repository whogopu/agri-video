"""Phase 3: text normalization, caption chunking/timing, narration with the stub backend."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pipeline.captions import build_captions, chunk_text
from pipeline.text_normalize import int_to_words, normalize, number_to_words

FIXTURE = Path(__file__).parent / "fixtures" / "sample-episode"
REPO = Path(__file__).parent.parent


@pytest.mark.parametrize("n,words", [
    (0, "शून्य"), (7, "सात"), (15, "पंद्रह"), (49, "उनचास"), (99, "निन्यानवे"), (100, "एक सौ"),
    (250, "दो सौ पचास"), (1000, "एक हज़ार"), (2026, "दो हज़ार छब्बीस"), (100000, "एक लाख"),
    (1250000, "बारह लाख पचास हज़ार"), (30000000, "तीन करोड़"),
])
def test_int_to_words(n, words):
    assert int_to_words(n) == words


@pytest.mark.parametrize("s,words", [
    ("1.5", "डेढ़"), ("2.5", "ढाई"), ("3.5", "साढ़े तीन"), ("1.25", "सवा"), ("2.25", "सवा दो"),
    ("2.75", "पौने तीन"), ("0.5", "आधा"), ("7.3", "सात दशमलव तीन"), ("2,500", "दो हज़ार पाँच सौ"),
    ("4.0", "चार"),
])
def test_number_to_words(s, words):
    assert number_to_words(s) == words


@pytest.mark.parametrize("text,spoken", [
    ("25 किलो यूरिया", "पच्चीस किलो यूरिया"),
    ("50kg/एकड़", "पचास किलो प्रति एकड़"),
    ("10-12 दिन", "दस से बारह दिन"),
    ("₹2,500", "दो हज़ार पाँच सौ रुपये"),
    ("25% छूट", "पच्चीस प्रतिशत छूट"),
    ("१५ सेमी", "पंद्रह सेंटीमीटर"),
    ("DAP डालें", "डी ए पी डालें"),
    ("10 lakh", "दस lakh"),  # 'l' unit must not eat the start of a word
])
def test_normalize(text, spoken):
    assert normalize(text, {"DAP": "डी ए पी"}) == spoken


def test_chunking_respects_max_words_and_punctuation():
    text = "नमूना खेत की कई जगहों से लें, लगभग पंद्रह सेंटीमीटर गहराई से, और सबको अच्छी तरह मिला लें।"
    chunks = chunk_text(text, 6)
    assert all(len(c.split()) <= 6 for c in chunks)
    assert " ".join(chunks) == text
    # a comma always ends a chunk
    assert any(c.endswith("लें,") for c in chunks) and any(c.endswith("से,") for c in chunks)
    # never start a chunk with a dangling postposition
    assert not any(c.split()[0] in {"में", "से", "को", "का", "की", "के"} for c in chunks)


def test_tiny_chunks_are_merged():
    assert chunk_text("हाँ, यही सही है।", 6) == ["हाँ, यही सही है।"]


def test_caption_timing_covers_duration():
    caps = build_captions("एक दो तीन चार, पाँच छह सात आठ नौ दस ग्यारह बारह।", 5.0, 4)
    assert caps[0].start == 0 and caps[-1].end == 5.0
    assert all(a.end == b.start for a, b in zip(caps, caps[1:]))


def test_narration_stub_end_to_end(tmp_path: Path):
    ep = tmp_path / "ep"
    shutil.copytree(FIXTURE, ep)
    py = [sys.executable, "-m"]
    subprocess.run(py + ["pipeline.text_normalize", str(ep)], check=True, cwd=REPO)
    subprocess.run(py + ["pipeline.narration", str(ep), "--backend", "stub", "--allow-unapproved"],
                   check=True, cwd=REPO, capture_output=True)
    data = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
    for s in data["scenes"]:
        assert (ep / s["audio"]["file"]).exists()
        assert s["audio"]["duration_sec"] > 0
        assert s["captions"] and s["captions"][-1]["end"] == pytest.approx(s["audio"]["duration_sec"])
    log = (ep / "log.md").read_text(encoding="utf-8")
    assert "LUFS" in log

    # unapproved script is refused without the testing flag
    r = subprocess.run(py + ["pipeline.narration", str(ep), "--backend", "stub"], cwd=REPO, capture_output=True, text=True)
    assert r.returncode != 0 and "not approved" in r.stderr + r.stdout


@pytest.mark.parametrize("text,bad_break", [
    ("मिट्टी की जांच से पता चलता है कि आपके खेत में कौन सा पोषक तत्व कम है और कौन सा पहले से काफ़ी है।", ("कौन", "सा")),
    ("क्या आप हर साल बिना जांच के खाद डालते हैं?", ("बिना", "जांच")),
    ("मिट्टी की जांच से पता चलता है कि आपके खेत में कौन सा पोषक तत्व कम है और कौन सा पहले से काफ़ी है।", ("पोषक", "तत्व")),
])
def test_no_break_inside_phrase(text, bad_break):
    chunks = chunk_text(text, 6)
    assert all(len(c.split()) <= 6 for c in chunks)
    for a, b in zip(chunks, chunks[1:]):
        assert (a.split()[-1], b.split()[0]) != bad_break, chunks


def test_slash_only_after_units():
    assert normalize("₹300/क्विंटल") == "तीन सौ रुपये प्रति क्विंटल"
    assert normalize("लैब/योजना") == "लैब/योजना"


def test_no_single_word_caption_in_lists():
    text = ("नाइट्रोजन, फॉस्फोरस, पोटाश और सल्फर, ज़िंक, आयरन, कॉपर, "
            "मैंगनीज़ और बोरॉन जैसे सूक्ष्म तत्व, और मिट्टी का pH, EC और जैविक कार्बन।")
    chunks = chunk_text(text, 6)
    assert all(len(c.split()) >= 2 for c in chunks), chunks
    assert all(len(c.split()) <= 7 for c in chunks)
