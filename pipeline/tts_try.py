"""Try TTS outside an episode: voice auditions and smoke tests.

    uv run python -m pipeline.tts_try --voices rohit aman          # config presets
    uv run python -m pipeline.tts_try --speakers Rohit Divya Aman Rani
    uv run python -m pipeline.tts_try --text "..." --text "..." --speakers Divya --out samples/voices

Each sentence is normalized (numbers → words, pronunciation.yaml), synthesized per speaker in
one model load, then resampled/trimmed/loudness-normalized like real narration. Prints a timing
table (seconds of compute per second of audio) for docs/timings.md.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from pipeline import audio
from pipeline.common import REPO_ROOT, load_config, setup_logging, voice_preset
from pipeline.text_normalize import load_pronunciations, normalize
from pipeline.tts_backends import TTSJob, get_backend

# Phase 3 acceptance sentences: numbers, units, English/Hinglish terms, a range and a price.
DEFAULT_SENTENCES = [
    "नमस्ते किसान भाइयों! आज हम बात करेंगे कि गेहूं की बुवाई से पहले मिट्टी की जांच क्यों ज़रूरी है।",
    "एक एकड़ में लगभग 40 किलो बीज लगता है, और DAP की मात्रा मिट्टी की जांच के बाद ही तय करें।",
    "स्प्रे करने से पहले दवा का लेबल ज़रूर पढ़ें, और 10-12 दिन बाद अपने नज़दीकी KVK से सलाह लें। जांच की फीस ₹50 है।",
]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--text", action="append", help="sentence (repeatable); default: 3 test sentences")
    p.add_argument("--voices", nargs="+", help="voice presets from config.yaml tts.voices")
    p.add_argument("--speakers", nargs="+", help="raw speaker names, using the default preset's description")
    p.add_argument("--backend", help="override config tts.backend")
    p.add_argument("--out", default="samples/voices", help="output folder (relative to repo)")
    p.add_argument("--description", help="override config tts.description ({speaker} is filled in)")
    p.add_argument("--tag", default="", help="suffix for file names, e.g. 'slow'")
    args = p.parse_args()
    setup_logging()

    cfg = load_config()
    base = {k: val for k, val in cfg["tts"].items() if k not in ("voices", "default_voice")}
    v = {**base, **voice_preset(cfg)}
    if args.backend:
        v["backend"] = args.backend
    backend = get_backend(v["backend"])
    pron = load_pronunciations()
    sentences = args.text or DEFAULT_SENTENCES
    spoken = [normalize(t, pron) for t in sentences]
    out_dir = REPO_ROOT / args.out
    raw_dir = out_dir / "raw"

    for i, (d, s) in enumerate(zip(sentences, spoken), 1):
        print(f"[{i}] display: {d}\n    spoken:  {s}")

    if args.voices:
        runs = [{**base, **voice_preset(cfg, name)} for name in args.voices]
    else:
        runs = [{**v, "speaker": sp} for sp in (args.speakers or [v["speaker"]])]
    if args.description:
        runs = [{**r, "description": args.description} for r in runs]

    rows = []
    for vs in runs:
        speaker = vs["speaker"]
        jobs = [TTSJob(s, raw_dir / f"{speaker.lower()}{'-' + args.tag if args.tag else ''}-{i}.wav") for i, s in enumerate(spoken, 1)]
        t0 = time.monotonic()
        results = backend.synthesize_many(jobs, vs)
        wall = time.monotonic() - t0
        for r in results:
            final = out_dir / r.out.name
            work = raw_dir / f"work-{r.out.name}"
            audio.resample_trim(r.out, work, int(cfg["tts"]["out_sample_rate"]))
            m = audio.measure_loudness([work])
            gain = float(cfg["audio"]["target_lufs"]) - m["lufs"]
            limit = float(cfg["audio"]["true_peak_db"]) - 0.5 if m["true_peak"] + gain > cfg["audio"]["true_peak_db"] else None
            audio.apply_gain(work, final, gain, limit)
            work.unlink()
            rows.append((speaker, final.name, r.sec_audio, r.sec_compute, r.device))
        print(f"{speaker}: {len(jobs)} clips, {wall:.1f}s wall including model load")

    print("\n| speaker | file | audio s | compute s | s compute / s audio | device |")
    print("|---|---|---|---|---|---|")
    for sp, f, a, c, dev in rows:
        print(f"| {sp} | {f} | {a:.2f} | {c:.1f} | {c / a if a else 0:.2f} | {dev} |")
    print(f"\nFiles: {out_dir.relative_to(REPO_ROOT)}/")


if __name__ == "__main__":
    main()
