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


# ---------- segment-level narration ----------

# ---- clean take edges -------------------------------------------------------------
# TTS takes often carry a short burst at the very start or end of the file that is not speech
# (Maya2/Mimi: ~20–30 ms of noise at about −40 dB after the speech has ended; Parler: a
# one-window blip). A plain silence trim keeps such a burst because it is "loud", and the join
# then cuts it off abruptly: an audible click/disturbance at every junction.

def speech_bounds(y, sr: int, floor_db: float = 40.0, min_island_ms: float = 60.0,
                  gap_ms: float = 50.0, with_limits: bool = False, edge_ms: float = 200.0):
    """(first, last) sample of the speech in a take. Speech = 10 ms windows within `floor_db` of the
    loudest window. A short 'island' (< min_island_ms) at either end, separated from the rest by
    ≥ gap_ms of quiet, is an artifact and ignored. with_limits=True also returns (lo, hi): how far
    padding may extend before/after the speech without reaching into a dropped artifact."""
    import numpy as np
    w = max(1, int(sr * 0.01))
    n = len(y) // w
    if n == 0:
        return (0, len(y), 0, len(y)) if with_limits else (0, len(y))
    env = 20 * np.log10(np.maximum(np.sqrt((y[: n * w].reshape(n, w) ** 2).mean(1)), 1e-9))
    loud = env > env.max() - floor_db
    idx = np.flatnonzero(loud)
    if idx.size == 0:
        return (0, len(y), 0, len(y)) if with_limits else (0, len(y))
    # group loud windows into islands separated by ≥ gap windows of quiet
    gap, isl_min = int(gap_ms / 10), int(min_island_ms / 10)
    islands, start, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - prev > gap:
            islands.append((start, prev))
            start = i
        prev = i
    islands.append((start, prev))
    # An island that runs into the very edge of the file, after a gap, is the model being cut off
    # mid-burst (Maya2 ends many takes with 70–80 ms at about −30 dB, still loud at the last sample).
    # Real speech decays into silence instead, so such an edge island is dropped up to `edge_ms`.
    edge = int(edge_ms / 10)
    def artifact(isl, at_start: bool) -> bool:
        length = isl[1] - isl[0] + 1
        if length < isl_min:
            return True
        touches = isl[0] <= 1 if at_start else isl[1] >= n - 2
        return touches and length < edge

    lo, hi = 0, len(y)
    while len(islands) > 1 and artifact(islands[0], True):
        lo = (islands.pop(0)[1] + 2) * w          # stay 10 ms clear of the dropped burst
    while len(islands) > 1 and artifact(islands[-1], False):
        hi = (islands.pop()[0] - 1) * w
    a, b = islands[0][0] * w, (islands[-1][1] + 1) * w
    return (a, b, lo, hi) if with_limits else (a, b)


def clean_take(src: Path, dst: Path, pre_ms: float = 40.0, post_ms: float = 90.0,
               fade_in_ms: float = 15.0, fade_out_ms: float = 60.0) -> None:
    """Cut a take to its speech (dropping edge artifacts), keep a little natural room before and
    after it, and apply smooth raised-cosine fades (no snap to silence)."""
    import numpy as np
    import soundfile as sf
    y, sr = sf.read(str(src), dtype="float32", always_2d=True)
    y = y.mean(1)
    a, b, lo, hi = speech_bounds(y, sr, with_limits=True)
    # natural room around the speech, but never reaching back into a dropped burst
    a = max(lo, a - int(sr * pre_ms / 1000))
    b = min(hi, b + int(sr * post_ms / 1000))
    y = y[a:b].copy()
    for ms, at_start in ((fade_in_ms, True), (fade_out_ms, False)):
        k = min(len(y) // 2, int(sr * ms / 1000))
        if k > 1:
            ramp = (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, k))).astype("float32")
            if at_start:
                y[:k] *= ramp
            else:
                y[-k:] *= ramp[::-1]
    dst.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(dst), y, sr, subtype="FLOAT")


_COMPRESS = "acompressor=threshold=0.1:ratio=3:attack=5:release=80"


def prepare_segment(src: Path, dst: Path, sample_rate: int, tempo: float = 1.0) -> None:
    """One TTS take → edges cleaned (clean_take), compressed, optional gentle tempo change
    (0.9–1.1), resampled. Joins are then smooth: speech decays into the take's own room, fades
    out over 60 ms, and the inserted pause sits on the same room tone."""
    clean = dst.with_name(dst.stem + "-clean.wav")
    clean_take(src, clean)
    af = _COMPRESS
    if abs(tempo - 1.0) > 1e-3:
        af += f",atempo={tempo:.3f}"
    af += f",aresample={sample_rate}"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(clean), "-af", af, "-ac", "1", "-c:a", "pcm_f32le", str(dst)])
    clean.unlink(missing_ok=True)


def join_with_pauses(parts: list[Path], pauses_sec: list[float], dst: Path, sample_rate: int) -> list[tuple[float, float]]:
    """Concatenate segments with silence between them (pauses_sec[i] follows parts[i]; the last
    is usually 0). Returns (start, end) of each part's speech in the joined file."""
    inputs: list[str] = []
    graph, labels, spans, t = [], [], [], 0.0
    for i, (p, pause) in enumerate(zip(parts, pauses_sec)):
        inputs += ["-i", str(p)]
        d = duration(p)
        spans.append((round(t, 3), round(t + d, 3)))
        labels.append(f"[{i}:a]")
        t += d
        if pause > 0 and i < len(parts) - 1:
            graph.append(f"aevalsrc=0:d={pause:.3f}:s={sample_rate}[p{i}]")
            labels.append(f"[p{i}]")
            t += pause
    graph.append("".join(labels) + f"concat=n={len(labels)}:v=0:a=1[out]")
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(graph), "-map", "[out]",
         "-ac", "1", "-c:a", "pcm_f32le", str(dst)])
    return spans


def make_room_tone(dst: Path, level_db: float, sample_rate: int = 48000, seconds: float = 30.0,
                   seed: int = 1) -> None:
    """A seamless loop of steady room tone: pink noise, 80 Hz–7 kHz, scaled to exactly `level_db`
    dBFS RMS. Played once under the whole video (Remotion, looped), not per scene, so it never
    switches on/off at scene changes. The loop's end is crossfaded into its start: no seam."""
    import numpy as np
    import soundfile as sf
    rng = np.random.default_rng(seed)
    xf = int(sample_rate * 0.5)
    n = int(sample_rate * seconds) + xf
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / sample_rate)
    spec *= np.where((f >= 80) & (f <= 7000), 1 / np.sqrt(np.maximum(f, 1)), 0)  # pink, band-limited
    y = np.fft.irfft(spec, n)
    body, tail = y[: n - xf].copy(), y[n - xf:]
    ramp = np.sin(np.linspace(0, np.pi / 2, xf)) ** 2                 # equal-power crossfade for noise
    body[:xf] = body[:xf] * np.sqrt(ramp) + tail * np.sqrt(1 - ramp)
    body *= 10 ** (level_db / 20) / np.sqrt(np.mean(body ** 2))
    dst.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(dst), body.astype("float32"), sample_rate, subtype="PCM_16")


def apply_gain_room_tone(src: Path, dst: Path, gain_db: float, limit_db: float | None,
                         room_tone_db: float | None, seed: int = 1) -> None:
    """(Unused since 2026-11-19: room tone in each scene file switched on/off at every scene change.
    Kept for scene-mode experiments; use make_room_tone + the Remotion room-tone track instead.)"""
    """apply_gain, then (optionally) mix in a very quiet, steady room tone so pauses are not
    digital silence. Pink noise, band-limited to 80 Hz–7 kHz, ~room_tone_db dBFS."""
    if room_tone_db is None:
        apply_gain(src, dst, gain_db, limit_db)
        return
    speech = f"[0:a]volume={gain_db:.2f}dB"
    if limit_db is not None:
        speech += f",alimiter=limit={10 ** (limit_db / 20):.4f}:level=disabled:attack=5:release=50"
    amp = 10 ** (room_tone_db / 20) * 3  # pink-noise RMS is roughly a third of its amplitude
    sr = int(run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate", "-of", "csv=p=0",
                  str(src)]).stdout.strip())
    graph = (f"{speech}[s];anoisesrc=color=pink:amplitude={amp:.6f}:sample_rate={sr}:seed={seed},"
             f"highpass=f=80,lowpass=f=7000[n];[s][n]amix=inputs=2:duration=first:normalize=0[out]")
    run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex", graph, "-map", "[out]",
         "-ac", "1", "-c:a", "pcm_s16le", str(dst)])
