"""Narration stage: one WAV per scene, loudness-normalized, plus caption timings.

    uv run python -m pipeline.narration episodes/<id> [--scene N] [--force] [--backend stub]

Per scene: TTS → audio/raw/scene-XX.wav (+ .json sidecar with what produced it)
           → resample to 48 kHz, trim silence → audio/work/scene-XX.wav
Episode:   measure integrated loudness over all scenes back to back, apply ONE gain
           to every scene (+ limiter if the true peak would exceed the ceiling)
           → audio/scene-XX.wav. Then duration_sec and captions go into episode.json.

Raw TTS is skipped when the sidecar shows the same text and voice (unless --force),
so `--scene N` only re-synthesizes that scene, but loudness is always recomputed
over the whole episode.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pipeline import audio
from pipeline.captions import build_captions
from pipeline.common import (
    format_config, load_config, voice_preset, load_episode, resolve_episode_dir, save_episode,
    selected_scenes, setup_logging, stage_parser, stage_timer,
)
from pipeline.schema import Audio, Episode, Status
from pipeline.tts_backends import TTSJob, get_backend, voice_description

LATIN_OR_DIGIT = re.compile(r"[A-Za-z0-9०-९]")


def voice_config(cfg: dict, ep: Episode) -> dict:
    """config.yaml tts settings, overridden by the episode's own voice (so an episode keeps its voice)."""
    v = {k: val for k, val in cfg["tts"].items() if k not in ("voices", "default_voice")}
    v.update(voice_preset(cfg, ep.voice.preset or None))
    for k, val in ep.voice.model_dump().items():
        if val not in (None, ""):
            v[k] = val
    return v


def job_key(text: str, v: dict) -> str:
    blob = json.dumps({"text": text, "backend": v["backend"], "model": v.get("model"),
                       "description": voice_description(v), "seed": v.get("seed")},
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()


def caption_max_words(cfg: dict, fmt: str) -> int:
    return int(format_config(cfg, fmt).get("caption_max_words", cfg["captions"]["max_words_per_chunk"]))


def main() -> None:
    p = stage_parser(__doc__)
    p.add_argument("--backend", help="override tts backend (e.g. stub for testing)")
    p.add_argument("--allow-unapproved", action="store_true",
                   help="testing only: narrate a script that hasn't passed checkpoint 1")
    args = p.parse_args()
    setup_logging(args.verbose)
    ep_dir = resolve_episode_dir(args.episode)
    cfg = load_config()

    with stage_timer(ep_dir, "narration") as run:
        ep = load_episode(ep_dir)
        if not ep.status.at_least(Status.script_approved) and not args.allow_unapproved:
            raise SystemExit("script is not approved yet (checkpoint 1). "
                             "Run `pipeline.validate <ep> --set-status script_approved` after approval.")
        empty = [s.id for s in ep.scenes if not s.narration_spoken.strip()]
        if empty:
            raise SystemExit(f"narration_spoken is empty for scenes {empty}; run pipeline.text_normalize first")

        v = voice_config(cfg, ep)
        if args.backend:
            v["backend"] = args.backend
        backend = get_backend(v["backend"])
        run.note(f"backend={backend.name} speaker={v.get('speaker')} seed={v.get('seed')}")

        raw_dir, work_dir, out_dir = ep_dir / "audio" / "raw", ep_dir / "audio" / "work", ep_dir / "audio"
        name = lambda s: f"scene-{s.id:02d}.wav"  # noqa: E731

        # 1. TTS for scenes whose raw audio is missing or stale
        jobs, keys = [], {}
        for s in selected_scenes(ep, args.scenes):
            raw, side = raw_dir / name(s), (raw_dir / name(s)).with_suffix(".json")
            key = job_key(s.narration_spoken, v)
            fresh = raw.exists() and side.exists() and json.loads(side.read_text()).get("key") == key
            if fresh and not args.force:
                continue
            jobs.append(TTSJob(s.narration_spoken, raw))
            keys[raw] = (key, s.narration_spoken)
        if jobs:
            results = backend.synthesize_many(jobs, v)
            for r in results:
                key, text = keys[r.out]
                r.out.with_suffix(".json").write_text(json.dumps(
                    {"key": key, "text": text, "backend": backend.name, "speaker": v.get("speaker"),
                     "sec_audio": r.sec_audio, "sec_compute": r.sec_compute, "device": r.device},
                    ensure_ascii=False, indent=2), encoding="utf-8")
                rtf = r.sec_compute / r.sec_audio if r.sec_audio else 0
                run.note(f"{r.out.name}: {r.sec_audio:.2f}s audio in {r.sec_compute:.1f}s ({rtf:.1f}× realtime, {r.device})")
        else:
            run.note("all raw narration up to date; skipping TTS")

        missing = [s.id for s in ep.scenes if not (raw_dir / name(s)).exists()]
        if missing:
            raise SystemExit(f"no raw audio for scenes {missing}; run narration without --scene first")

        # 2. resample + trim every scene (cheap), 3. one loudness gain for the whole episode
        sr = int(cfg["tts"]["out_sample_rate"])
        for s in ep.scenes:
            audio.resample_trim(raw_dir / name(s), work_dir / name(s), sr)
        work = [work_dir / name(s) for s in ep.scenes]
        before = audio.measure_loudness(work)
        target, ceiling = float(cfg["audio"]["target_lufs"]), float(cfg["audio"]["true_peak_db"])
        gain = target - before["lufs"]
        limit = ceiling - 0.5 if before["true_peak"] + gain > ceiling else None
        for _ in range(3):  # the limiter lowers loudness a little; top up the gain until within 0.5 LU
            for s in ep.scenes:
                audio.apply_gain(work_dir / name(s), out_dir / name(s), gain, limit)
            after = audio.measure_loudness([out_dir / name(s) for s in ep.scenes])
            if abs(after["lufs"] - target) <= 0.5:
                break
            gain += target - after["lufs"]
        run.note(f"loudness {before['lufs']:.1f} → {after['lufs']:.1f} LUFS (target {target}), "
                 f"true peak {after['true_peak']:.1f} dBTP, gain {gain:+.1f} dB"
                 + (", limiter on" if limit is not None else ""))

        # 4. durations + captions into episode.json
        max_words = caption_max_words(cfg, ep.format)
        for s in ep.scenes:
            dur = round(audio.duration(out_dir / name(s)), 3)
            s.audio = Audio(file=f"audio/{name(s)}", duration_sec=dur)
            s.captions = build_captions(s.narration_display, dur, max_words)
        save_episode(ep_dir, ep)
        total = sum(s.audio.duration_sec for s in ep.scenes if s.audio)
        run.note(f"{len(ep.scenes)} scenes, narration total {total:.1f}s")

    # quick-listen list: first two scenes + scenes with numbers or English terms
    check = [s for s in ep.scenes if s.id <= ep.scenes[0].id + 1 or LATIN_OR_DIGIT.search(s.narration_display)]
    print("\nListen to these (first two scenes + any with numbers or English terms):")
    for s in check:
        print(f"  {ep_dir.name}/audio/{name(s)}  — {s.narration_display[:70]}")


if __name__ == "__main__":
    main()
