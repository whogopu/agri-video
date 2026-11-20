"""Take-scoring worker. Runs in the isolated asr/ env (mlx-whisper + librosa).

    uv run --project asr python asr/asr_worker.py < request.json

Request (stdin, JSON):
    {"model": "mlx-community/whisper-large-v3-turbo", "language": "hi",
     "jobs": [{"wav": "/abs/take.wav"}]}

For each job prints one JSON line to stdout:
    {"wav": ..., "text": "<what whisper heard>", "speech_sec": 3.9, "f0_range_st": 7.2,
     "end_rise_st": 1.4, "max_gap_sec": 0.21, "sec_compute": 1.1}

- text:        transcription (temperature 0, no prompt, so it doesn't lean towards the script)
- speech_sec:  first to last non-silent frame
- f0_range_st: pitch spread in semitones (10th–90th percentile of voiced frames); low = monotone
- end_rise_st: pitch of the last 20% of voiced frames minus the rest (questions should rise)
- f0_median_hz: typical pitch of the take (sentences should sit in the same register)
- max_gap_sec: longest silence inside the speech (odd mid-sentence gaps)
Scoring itself happens in pipeline/take_scoring.py, so weights can change without this env.

Word timing (pipeline/word_align.py): a job with "words": true (optionally "prompt": the script)
also returns
    "words":    [{"w": "मिट्टी", "start": 0.42, "end": 0.81}, ...]   (whisper word_timestamps)
    "silences": [[1.74, 2.31], ...]   quiet runs >= "silence_min_sec" (default 0.08), quieter than
                                      the loudest frame by "silence_db" (default 35)
The prompt only helps Whisper spell the words as written (better letter alignment); scoring
jobs never send one, so a slip in a take is still heard as a slip.
"""

from __future__ import annotations

import json
import sys
import time

import librosa
import mlx_whisper
import numpy as np

SR = 16000
FRAME = 320  # 20 ms


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def silence_features(y: np.ndarray) -> tuple[float, float]:
    rms = librosa.feature.rms(y=y, frame_length=FRAME * 2, hop_length=FRAME)[0]
    db = 20 * np.log10(np.maximum(rms, 1e-8))
    voiced = db > (db.max() - 40)
    idx = np.flatnonzero(voiced)
    if idx.size == 0:
        return 0.0, 0.0
    first, last = idx[0], idx[-1]
    longest = run = 0
    for v in voiced[first:last + 1]:
        run = 0 if v else run + 1
        longest = max(longest, run)
    hop = FRAME / SR
    return float((last - first + 1) * hop), float(longest * hop)


def pitch_features(y: np.ndarray) -> tuple[float, float, float]:
    f0, voiced, _ = librosa.pyin(y, fmin=65, fmax=400, sr=SR, frame_length=1024, hop_length=FRAME)
    f0 = f0[voiced & ~np.isnan(f0)]
    if f0.size < 10:
        return 0.0, 0.0, 0.0
    st = 12 * np.log2(f0 / np.median(f0))
    rng = float(np.percentile(st, 90) - np.percentile(st, 10))
    cut = int(len(st) * 0.8)
    rise = float(np.median(st[cut:]) - np.median(st[:cut]))
    return rng, rise, float(np.median(f0))


def silences(y: np.ndarray, below_db: float, min_sec: float) -> list[list[float]]:
    hop = 160  # 10 ms
    rms = librosa.feature.rms(y=y, frame_length=640, hop_length=hop)[0]
    db = 20 * np.log10(np.maximum(rms, 1e-8))
    quiet = np.r_[False, db < db.max() - below_db, False]
    d = np.diff(quiet.astype(int))
    starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    return [[round(a * hop / SR, 3), round(b * hop / SR, 3)] for a, b in zip(starts, ends)
            if (b - a) * hop / SR >= min_sec]


def main() -> None:
    req = json.load(sys.stdin)
    model, lang = req.get("model", "mlx-community/whisper-large-v3-turbo"), req.get("language", "hi")
    for i, job in enumerate(req["jobs"], 1):
        t0 = time.monotonic()
        y, _ = librosa.load(job["wav"], sr=SR, mono=True)
        want_words = bool(job.get("words"))
        res = mlx_whisper.transcribe(job["wav"], path_or_hf_repo=model, language=lang, temperature=0.0,
                                     condition_on_previous_text=False, verbose=None,
                                     word_timestamps=want_words, initial_prompt=job.get("prompt") or None)
        speech, gap = silence_features(y)
        rng, rise, med = (0.0, 0.0, 0.0) if want_words else pitch_features(y)  # pitch only matters for scoring
        out = {"wav": job["wav"], "text": res.get("text", "").strip(), "speech_sec": round(speech, 3),
               "f0_range_st": round(rng, 2), "end_rise_st": round(rise, 2), "f0_median_hz": round(med, 1), "max_gap_sec": round(gap, 3),
               "sec_compute": round(time.monotonic() - t0, 2)}
        if want_words:
            out["words"] = [{"w": w["word"].strip(), "start": round(float(w["start"]), 3), "end": round(float(w["end"]), 3)}
                            for seg in res.get("segments", []) for w in seg.get("words", []) if w["word"].strip()]
            out["silences"] = silences(y, float(job.get("silence_db", 35)), float(job.get("silence_min_sec", 0.08)))
        log(f"[{i}/{len(req['jobs'])}] {out['sec_compute']}s  {out['text'][:60]}")
        print(json.dumps(out, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
