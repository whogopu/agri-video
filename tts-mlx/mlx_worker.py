"""MLX TTS worker (mlx-audio). Runs inside the isolated tts-mlx/ env.

    uv run --project tts-mlx python tts-mlx/mlx_worker.py < request.json

Request (stdin, JSON):
    {"model": "maya-research/maya2-native", "lang": "hi",
     "jobs": [{"text": "...", "out": "/abs/path.wav", "seed": 42,
               "voice": "Siddhant",                    # built-in voice (Maya2), or
               "ref_audio": "/abs/ref.wav", "ref_text": "...",   # reference clip (Chatterbox / cloning)
               "params": {"exaggeration": 0.6}}]}      # model-specific generate() kwargs

Loads the model once. For each job writes a mono WAV and prints one JSON line:
    {"out": ..., "sec_audio": 4.2, "sec_compute": 3.1, "device": "mlx", "sample_rate": 24000}
"""

from __future__ import annotations

import json
import sys
import time

import mlx.core as mx
import numpy as np
import soundfile as sf
from mlx_audio.tts.utils import load


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def main() -> None:
    req = json.load(sys.stdin)
    t0 = time.monotonic()
    model = load(req["model"])
    log(f"{req['model']} loaded in {time.monotonic() - t0:.1f}s")
    lang = req.get("lang", "hi")
    for i, job in enumerate(req["jobs"], 1):
        t0 = time.monotonic()
        seed = int(job.get("seed", 42))
        mx.random.seed(seed)
        np.random.seed(seed)
        kw = {"lang_code": lang, **(job.get("params") or {})}
        if job.get("voice"):
            kw["voice"] = job["voice"]
        if job.get("ref_audio"):
            kw["ref_audio"] = job["ref_audio"]
            if job.get("ref_text"):
                kw["ref_text"] = job["ref_text"]
        chunks, sr = [], None
        for res in model.generate(job["text"], **kw):
            chunks.append(np.asarray(res.audio, dtype=np.float32).reshape(-1))
            sr = res.sample_rate
        audio = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
        sf.write(job["out"], audio, sr)
        out = {"out": job["out"], "sec_audio": round(len(audio) / sr, 3),
               "sec_compute": round(time.monotonic() - t0, 2), "device": "mlx", "sample_rate": sr}
        log(f"[{i}/{len(req['jobs'])}] {out['sec_audio']}s audio in {out['sec_compute']}s")
        print(json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
