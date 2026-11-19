---
name: narration
description: Generate per-scene Hindi narration audio and caption timings for an approved AgriGate episode. Use after checkpoint 1, or to redo narration for specific scenes.
---

# narration

Requires status `script_approved`.

```bash
uv run python -m pipeline.text_normalize episodes/<id>      # if narration_spoken is empty
uv run python -m pipeline.narration episodes/<id> [--scene N] [--force]
uv run python -m pipeline.validate episodes/<id> --set-status narrated
```

- Backend from `config.yaml: tts` (default Indic Parler-TTS, fixed speaker/description/seed, MPS with CPU fallback).
- One WAV per scene → 48 kHz, silence trimmed, loudness normalized; `audio.duration_sec` and `captions` written to `episode.json`.
- The voice comes from `episode.json: voice` (copied from config at creation), so an episode keeps one voice even if config changes.
- Raw TTS is cached per scene (`audio/raw/*.json` sidecar). Changing the text or voice re-synthesizes only those scenes; loudness is always re-done over the whole episode.
- Parler runs on MPS, in the `tts/` env (gated model: needs `hf auth login`). Expect several seconds of compute per second of audio; run nothing else heavy at the same time.
- Mispronunciation? Add a fix to `pronunciation.yaml`, rebuild `narration_spoken`, rerun with `--scene N --force`.
- Don't play audio automatically. Tell the user which files to check: scenes 1–2 plus every scene with numbers or English terms.
