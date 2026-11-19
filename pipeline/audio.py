"""ffmpeg/ffprobe helpers: duration, resample + trim, loudness measure and gain."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed ({res.returncode}): {res.stderr[-2000:]}")
    return res


def duration(path: Path) -> float:
    res = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    return float(res.stdout.strip())


# keep ~60 ms of room before/after speech so words don't start abruptly
_TRIM = ("silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.06:detection=peak,"
         "areverse,"
         "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.06:detection=peak,"
         "areverse,"
         # gentle 3:1 compression above −20 dBFS: TTS is peaky, and without this the
         # true-peak limiter eats the loudness gain
         "acompressor=threshold=0.1:ratio=3:attack=5:release=80")


def resample_trim(src: Path, dst: Path, sample_rate: int) -> None:
    """Mono, resampled, leading/trailing silence removed. 32-bit float to keep headroom for gain."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", f"{_TRIM},aresample={sample_rate}",
         "-ac", "1", "-c:a", "pcm_f32le", str(dst)])


def measure_loudness(paths: list[Path]) -> dict[str, float]:
    """Integrated loudness (LUFS) and true peak (dBTP) over the files played back to back."""
    inputs: list[str] = []
    for p in paths:
        inputs += ["-i", str(p)]
    n = len(paths)
    graph = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1,loudnorm=print_format=json"
    res = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *inputs, "-filter_complex", graph, "-f", "null", "-"],
                         capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", res.stderr, re.S)
    if not m:
        raise RuntimeError(f"loudness measurement failed: {res.stderr[-1500:]}")
    d = json.loads(m.group(0))
    return {"lufs": float(d["input_i"]), "true_peak": float(d["input_tp"])}


def apply_gain(src: Path, dst: Path, gain_db: float, limit_db: float | None) -> None:
    """Static gain (same for every scene, so relative levels stay natural), optional peak limiter."""
    af = f"volume={gain_db:.2f}dB"
    if limit_db is not None:
        af += f",alimiter=limit={10 ** (limit_db / 20):.4f}:level=disabled:attack=5:release=50"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", af, "-c:a", "pcm_s16le", str(dst)])
