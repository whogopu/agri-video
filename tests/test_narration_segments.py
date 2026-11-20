"""Sentence-level narration: markup parsing, take scoring, segment captions, stub end to end."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pipeline.narration import segment_captions
from pipeline.prosody import auto_style, paired_segments, split_segments, strip_markup
from pipeline.take_scoring import TakeMetrics, canon, cer, score_takes
from pipeline.text_normalize import normalize
from pipeline.validate import count_words

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "sample-episode"
RULES = {"question": "question", "digits": "slow", "purpose": {"cta": "warm"}}


def test_split_sentences_and_pause_marks():
    segs = split_segments("क्या आप खाद डालते हैं? || हो सकता है | पैसा बेकार जा रहा हो। {slow} 10 से 15 जगहें चुनें!")
    assert [s.text for s in segs] == ["क्या आप खाद डालते हैं?", "हो सकता है", "पैसा बेकार जा रहा हो।", "10 से 15 जगहें चुनें!"]
    assert [s.pause for s in segs] == ["long", "short", "sentence", "end"]
    assert segs[3].style == "slow"


def test_plain_text_splits_on_sentences_only():
    segs = split_segments("पहली गलती, एक कोने से नमूना लेना। तब रिपोर्ट गलत होगी।")
    assert [s.text for s in segs] == ["पहली गलती, एक कोने से नमूना लेना।", "तब रिपोर्ट गलत होगी।"]
    assert [s.pause for s in segs] == ["sentence", "end"]


def test_strip_markup_and_word_count():
    t = "अब तरीका। || {slow} 10 से 15 जगहें | चुनें।"
    assert strip_markup(t) == "अब तरीका। 10 से 15 जगहें चुनें।"
    assert count_words(t) == 7


def test_markup_survives_normalize_and_pairs():
    display = "अब तरीका। || {slow} 10 से 15 जगहें चुनें।"
    pairs = paired_segments(display, normalize(display))
    assert pairs[1][0].text == "10 से 15 जगहें चुनें।" and pairs[1][1].text == "दस से पंद्रह जगहें चुनें।"
    with pytest.raises(ValueError):
        paired_segments("हो सकता है | आपके खेत को।", "हो सकता है आपके खेत को।")  # spoken lost the | mark


def test_auto_style():
    seg = lambda t: split_segments(t)[0]  # noqa: E731
    assert auto_style(seg("क्या आप जानते हैं?"), "क्या आप जानते हैं?", "hook", 0, RULES) == "question"
    assert auto_style(seg("दस जगहें"), "10 जगहें", "step", 0, RULES) == "slow"
    assert auto_style(seg("सब्सक्राइब करें।"), "सब्सक्राइब करें।", "cta", 0, RULES) == "warm"
    assert auto_style(seg("{firm} सब्सक्राइब करें।"), "", "cta", 0, RULES) == "firm"
    assert auto_style(seg("नमूना लें।"), "नमूना लें।", "step", 0, RULES) == "neutral"


def test_cer_ignores_whisper_spelling_quirks():
    assert cer("ज़रूरत है, दस से पंद्रह।", "जरूरत है 10 से 15") == 0
    assert cer("डी ए पी डालें", "DAP डालें") == 0  # pronunciation.yaml applied to what was heard
    assert cer("आपके खेत को", "आपके खेट को") > 0
    assert canon("कॉपर") == canon("कापर")


def test_scoring_prefers_accurate_and_rejects_babble():
    ref = "क्या आप हर साल खाद डालते हैं?"
    good = TakeMetrics(heard=ref, speech_sec=3.0, f0_range_st=6, end_rise_st=1.5, max_gap_sec=0.2)
    wrong_word = TakeMetrics(heard="क्या आप हर साल खाट डालते हैं", speech_sec=3.0, f0_range_st=7, end_rise_st=1.5, max_gap_sec=0.2)
    babble = TakeMetrics(heard=ref + " और कुछ", speech_sec=4.6, f0_range_st=6, end_rise_st=1.5, max_gap_sec=0.2)
    flat = TakeMetrics(heard=ref, speech_sec=3.0, f0_range_st=2, end_rise_st=-1, max_gap_sec=0.2)
    for t in (good, wrong_word, babble, flat):
        t.cer = cer(ref, t.heard)
    scores = score_takes(ref, [good, wrong_word, babble, flat])
    assert scores.index(max(scores)) == 0
    assert scores[2] == min(scores)


def test_segment_captions_follow_speech():
    caps = segment_captions(["पहला वाक्य यहाँ है।", "दूसरा वाक्य।"], [(0.06, 2.0), (2.6, 4.0)], 4.06, 6)
    assert caps[0].start == 0 and caps[-1].end == pytest.approx(4.06)
    second = [c for c in caps if "दूसरा" in c.text][0]
    assert second.start == pytest.approx(2.6)          # starts when its sentence is spoken
    assert all(a.end == b.start for a, b in zip(caps, caps[1:]))  # no flicker in pauses


def test_segment_narration_stub_end_to_end(tmp_path: Path):
    ep = tmp_path / "ep"
    shutil.copytree(FIXTURE, ep)
    data = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
    data["scenes"][0]["narration_display"] = "क्या आप हर साल खाद डालते हैं? || {slow} 10 से 15 जगहें | चुनें।"
    data["scenes"][0]["narration_spoken"] = ""
    (ep / "episode.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    py = [sys.executable, "-m"]
    subprocess.run(py + ["pipeline.text_normalize", str(ep)], check=True, cwd=REPO)
    base = py + ["pipeline.narration", str(ep), "--backend", "stub", "--allow-unapproved", "--mode", "segments", "--takes", "2"]
    subprocess.run(base, check=True, cwd=REPO, capture_output=True)

    data = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
    s0 = data["scenes"][0]
    segs = s0["audio"]["segments"]
    assert [x["style"] for x in segs] == ["question", "slow", "slow"]
    assert segs[1]["start"] - segs[0]["end"] > 0.5  # the || pause
    assert all("|" not in c["text"] and "{" not in c["text"] for c in s0["captions"])
    assert s0["captions"][-1]["end"] == pytest.approx(s0["audio"]["duration_sec"])
    assert (ep / "audio" / "takes.md").exists()
    manifest = json.loads((ep / "audio" / "segments" / "scene-01.json").read_text())
    assert len(manifest) == 3 and all(len(m["takes"]) == 2 for m in manifest)
    # word timings (stub audio → proportional, inside each segment's span, in order)
    words = s0["audio"]["words"]
    assert [w["text"] for w in words] == "क्या आप हर साल खाद डालते हैं? 10 से 15 जगहें चुनें।".split()
    for w in words:
        seg = segs[w["segment"]]
        assert seg["start"] - 1e-6 <= w["start"] < w["end"] <= seg["end"] + 1e-6
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(words, words[1:]))

    # a manual pick sticks across reruns while the segment text is unchanged
    subprocess.run(base + ["--pick", "1:2:2"], check=True, cwd=REPO, capture_output=True)
    subprocess.run(base, check=True, cwd=REPO, capture_output=True)
    manifest = json.loads((ep / "audio" / "segments" / "scene-01.json").read_text())
    assert manifest[1]["chosen"] == 2 and manifest[1]["override"] == 2


def test_scoring_prefers_takes_in_the_episode_register():
    ref = "अब नमूना लेने का तरीका।"
    mk = lambda hz: TakeMetrics(heard=ref, cer=0.0, speech_sec=1.7, f0_range_st=8, max_gap_sec=0.1, f0_median_hz=hz)  # noqa: E731
    scores = score_takes(ref, [mk(180), mk(140), mk(118)], ref_f0_hz=140)
    assert scores.index(max(scores)) == 1


def test_take_cache_key_separates_voices_and_models():
    from pipeline.narration import take_key
    maya = {"backend": "mlx_audio", "model": "maya-research/maya2-native", "speaker": "Vasant", "params": {"normalize": False}}
    keys = {
        take_key("नमूना लें।", maya, "", 42),
        take_key("नमूना लें।", {**maya, "speaker": "Satvik"}, "", 42),
        take_key("नमूना लें।", {**maya, "model": "maya-research/Veena", "speaker": "varun"}, "", 42),
        take_key("नमूना लें।", maya, "", 43),
        take_key("नमूना लें।", maya, "", 42, {"exaggeration": 0.6}),
    }
    assert len(keys) == 5


def test_scoring_rejects_a_take_in_a_different_voice():
    # Veena drift: same sentence, one take ~230 Hz (the voice), others ~125 Hz with fewer slips
    ref = "दस से पंद्रह जगहें चुनें।"
    right_voice = TakeMetrics(heard="दस से पंद्रह जगे चुनें", speech_sec=3, f0_range_st=8, max_gap_sec=0.2, f0_median_hz=232)
    drifted = TakeMetrics(heard=ref, speech_sec=3, f0_range_st=8, max_gap_sec=0.2, f0_median_hz=125)
    for t in (right_voice, drifted):
        t.cer = cer(ref, t.heard)
    scores = score_takes(ref, [right_voice, drifted, drifted], ref_f0_hz=140, voice_f0_hz=228)
    assert scores[0] > scores[1]


def test_clean_take_drops_edge_bursts_but_keeps_speech(tmp_path: Path):
    import numpy as np
    import soundfile as sf
    from pipeline.audio import clean_take, speech_bounds
    sr = 24000
    t = np.arange(int(sr * 0.6)) / sr
    word = 0.3 * np.sin(2 * np.pi * 150 * t)                       # 600 ms "speech"
    short_word = 0.2 * np.sin(2 * np.pi * 150 * t[: int(sr * 0.12)])  # a short last word, 120 ms
    quiet = np.zeros(int(sr * 0.1))
    burst = 0.01 * np.random.default_rng(0).standard_normal(int(sr * 0.025))  # ~-40 dB codec burst
    y = np.concatenate([burst, quiet, word, quiet[: int(sr * 0.06)], short_word, quiet, burst]).astype("float32")
    a, b = speech_bounds(y, sr)
    start_word = len(burst) + len(quiet)
    end_short = start_word + len(word) + int(sr * 0.06) + len(short_word)
    assert abs(a - start_word) <= sr * 0.01 and abs(b - end_short) <= sr * 0.01  # bursts dropped, short word kept
    src, dst = tmp_path / "take.wav", tmp_path / "clean.wav"
    sf.write(src, y, sr)
    clean_take(src, dst)
    out, _ = sf.read(dst)
    assert abs(out[0]) < 1e-4 and abs(out[-1]) < 1e-4                # fades end at silence: no click
    assert len(out) == pytest.approx(end_short - start_word + sr * 0.13, abs=sr * 0.02)


def test_voice_pronunciation_changes_only_tts_text():
    from pipeline.common import load_config
    from pipeline.narration import plan_scene
    from pipeline.schema import Scene
    s = Scene(id=1, purpose="cta", narration_display="जांच से खाद सही लगती है।", narration_spoken="जांच से खाद सही लगती है।")
    v = {"backend": "mlx_audio", "model": "m", "speaker": "Vasant", "seed": 42, "pronunciation": {"जांच": "जाञ्च"}}
    seg = plan_scene(s, load_config(), v, 2, Path("/tmp"))[0]
    assert seg["tts_text"] == "जाञ्च से खाद सही लगती है।"
    assert seg["spoken"] == "जांच से खाद सही लगती है।"  # scoring reference keeps the normal spelling
    plain = plan_scene(s, load_config(), {**v, "pronunciation": {}}, 2, Path("/tmp"))[0]
    assert plain["takes"][0]["file"] != seg["takes"][0]["file"]


def test_post_roll_never_reaches_a_dropped_burst(tmp_path: Path):
    # burst 60 ms after the last word: inside the 90 ms post-roll, but must not come back
    import numpy as np
    import soundfile as sf
    from pipeline.audio import clean_take
    sr = 24000
    t = np.arange(int(sr * 0.5)) / sr
    word = (0.3 * np.sin(2 * np.pi * 150 * t)).astype("float32")
    gap = np.zeros(int(sr * 0.06), dtype="float32")
    burst = (0.02 * np.random.default_rng(1).standard_normal(int(sr * 0.025))).astype("float32")
    src, dst = tmp_path / "take.wav", tmp_path / "clean.wav"
    sf.write(src, np.concatenate([word, gap, burst]), sr)
    clean_take(src, dst)
    out, _ = sf.read(dst)
    tail = out[len(word) + int(sr * 0.02):]  # everything after the word (beyond pre-roll slack)
    assert len(out) < len(word) + int(sr * 0.1) and (len(tail) == 0 or np.abs(tail).max() < 0.005)


def test_room_tone_level_and_seamless_loop(tmp_path: Path):
    import numpy as np
    import soundfile as sf
    from pipeline.audio import make_room_tone
    p = tmp_path / "rt.wav"
    make_room_tone(p, -66.0, 48000, seconds=4.0)
    y, sr = sf.read(p)
    assert abs(20 * np.log10(np.sqrt(np.mean(y ** 2))) - (-66.0)) < 0.5
    looped = np.concatenate([y, y])
    w = int(sr * 0.01)
    env = lambda a: 20 * np.log10(np.sqrt(np.mean(a ** 2)) + 1e-12)  # noqa: E731
    seam = env(looped[len(y) - w: len(y) + w])
    assert abs(seam - (-66.0)) < 3.0  # no level step or click at the loop point


def test_loud_burst_running_into_file_end_is_dropped():
    # Maya2: speech, ~100 ms near-silence, then ~80 ms at about -30 dB that is cut off at the last sample
    import numpy as np
    from pipeline.audio import speech_bounds
    sr = 24000
    t = np.arange(int(sr * 0.8)) / sr
    word = 0.3 * np.sin(2 * np.pi * 150 * t)
    quiet = 0.0002 * np.random.default_rng(2).standard_normal(int(sr * 0.1))
    burst = 0.03 * np.random.default_rng(3).standard_normal(int(sr * 0.08))
    y = np.concatenate([word, quiet, burst])
    a, b = speech_bounds(y, sr)
    assert abs(b - len(word)) <= sr * 0.01
    # but a genuine last word that decays (not cut at the file end) after a pause is kept
    last = 0.3 * np.sin(2 * np.pi * 150 * t[: int(sr * 0.15)]) * np.linspace(1, 0, int(sr * 0.15))
    y2 = np.concatenate([word, quiet, last, np.zeros(int(sr * 0.1))])
    _, b2 = speech_bounds(y2, sr)
    assert b2 > len(word) + len(quiet)
