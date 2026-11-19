"""Score TTS takes so the best one per segment can be picked automatically.

Each take is transcribed by Whisper (asr/ env, subprocess) and measured for pitch and gaps.
Scores only RANK takes of the same segment against each other: Whisper's own Hindi spelling
quirks (ज़/ज, nasal marks, digits) hit every take equally, so a relative comparison is still
meaningful even though the absolute error rate is noisy.

score =  - w.cer        * character error rate (wrong / missing / extra words; babble at the end)
         - w.length     * how far the speech length is from the median of the takes (log ratio, beyond ±10%)
         + w.expressive * pitch range in semitones, capped (monotone takes lose)
         - w.gap        * longest mid-sentence silence beyond `gap_ok_sec`
         + w.question   * pitch rise at the end, for segments ending in '?'
         - w.register   * semitones between the take's median pitch and the episode's typical pitch,
                          beyond `register_ok_st`, per delivery style (a take much higher/lower than
                          others of its style sounds like a different delivery)
         - w.identity   * semitones between the take and the episode's overall voice pitch beyond
                          `identity_ok_st`: a take that far off is effectively a different speaker
                          (Veena sometimes drifts from a ~230 Hz voice to ~120 Hz), so it should lose
                          even against a take with a wrong word
A one-word slip (cer ≈ 0.03) costs ~6 points, more than any pitch preference: accuracy first,
except for a different-sounding speaker.
"""

from __future__ import annotations

import json
import math
import re
import statistics
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.common import REPO_ROOT, log
from functools import lru_cache

from pipeline.text_normalize import load_pronunciations, normalize

ASR_PROJECT = REPO_ROOT / "asr"

DEFAULT_WEIGHTS = {"cer": 200.0, "length": 40.0, "expressive": 1.5, "expressive_cap": 9.0,
                   "gap": 15.0, "gap_ok_sec": 0.45, "question": 2.0,
                   "register": 2.5, "register_ok_st": 1.5,
                   "identity": 10.0, "identity_ok_st": 4.0}


@dataclass
class TakeMetrics:
    heard: str = ""
    cer: float | None = None
    speech_sec: float = 0.0
    f0_range_st: float = 0.0
    end_rise_st: float = 0.0
    max_gap_sec: float = 0.0
    f0_median_hz: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


# ---------- text comparison ----------

_STRIP = re.compile(r"[\s\.,;:!?।'\"“”‘’\-–—()]+")


@lru_cache(maxsize=1)
def _pron() -> dict[str, str]:
    return load_pronunciations()


def canon(text: str) -> str:
    """Normalize Hindi text for comparison: numbers → words, drop nukta and punctuation,
    unify nasal marks and a few spellings Whisper varies on."""
    t = normalize(text, _pron())
    t = t.replace("़", "")            # nukta: ज़ → ज
    t = t.replace("ँ", "ं")                  # chandrabindu → anusvara
    t = t.replace("ॉ", "ा").replace("ऑ", "आ")
    return _STRIP.sub("", t)


def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(reference: str, heard: str) -> float:
    r, h = canon(reference), canon(heard)
    return levenshtein(r, h) / max(1, len(r))


# ---------- scoring ----------

def score_takes(reference: str, takes: list[TakeMetrics], weights: dict | None = None,
                ref_f0_hz: float | None = None, voice_f0_hz: float | None = None) -> list[float]:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    lengths = [t.speech_sec for t in takes if t.speech_sec > 0]
    median = statistics.median(lengths) if lengths else 0.0
    question = reference.rstrip().endswith("?")
    scores = []
    for t in takes:
        s = 0.0
        if t.cer is not None:
            s -= w["cer"] * t.cer
        if median and t.speech_sec:
            s -= w["length"] * max(0.0, abs(math.log(t.speech_sec / median)) - 0.10)
        s += w["expressive"] * min(t.f0_range_st, w["expressive_cap"])
        s -= w["gap"] * max(0.0, t.max_gap_sec - w["gap_ok_sec"])
        if question:
            s += w["question"] * max(-2.0, min(t.end_rise_st, 3.0))
        if ref_f0_hz and t.f0_median_hz:
            off = abs(12 * math.log2(t.f0_median_hz / ref_f0_hz))
            s -= w["register"] * max(0.0, off - w["register_ok_st"])
        if voice_f0_hz and t.f0_median_hz:
            off = abs(12 * math.log2(t.f0_median_hz / voice_f0_hz))
            s -= w["identity"] * max(0.0, off - w["identity_ok_st"])
        scores.append(round(s, 2))
    return scores


# ---------- ASR backend ----------

def measure(wavs: list[Path], asr_cfg: dict) -> dict[Path, TakeMetrics]:
    """Transcribe + measure takes. backend 'whisper' (asr/ env) or 'none' (lengths only; for tests)."""
    backend = asr_cfg.get("backend", "whisper")
    if not wavs:
        return {}
    if backend == "none":
        from pipeline.audio import duration
        return {w: TakeMetrics(speech_sec=duration(w)) for w in wavs}
    if backend != "whisper":
        raise SystemExit(f"unknown narration.asr.backend {backend!r} (whisper | none)")
    req = {"model": asr_cfg.get("model", "mlx-community/whisper-large-v3-turbo"),
           "language": asr_cfg.get("language", "hi"),
           "jobs": [{"wav": str(w)} for w in wavs]}
    cmd = ["uv", "run", "--project", str(ASR_PROJECT), "python", str(ASR_PROJECT / "asr_worker.py")]
    log.info("scoring %d take(s) with %s", len(wavs), req["model"])
    proc = subprocess.run(cmd, input=json.dumps(req), stdout=subprocess.PIPE, stderr=None, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"asr worker failed (exit {proc.returncode}); see messages above")
    out: dict[Path, TakeMetrics] = {}
    for line in proc.stdout.splitlines():
        if line.startswith("{"):
            d = json.loads(line)
            out[Path(d["wav"])] = TakeMetrics(heard=d["text"], speech_sec=d["speech_sec"],
                                              f0_range_st=d["f0_range_st"], end_rise_st=d["end_rise_st"],
                                              max_gap_sec=d["max_gap_sec"], f0_median_hz=d.get("f0_median_hz", 0.0))
    missing = [w for w in wavs if w not in out]
    if missing:
        raise RuntimeError(f"asr worker returned no result for {len(missing)} take(s)")
    return out
