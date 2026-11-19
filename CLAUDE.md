# AgriGate Hindi Video Pipeline

Hindi educational YouTube videos for North Indian farmers: an AI narrator explains a topic over B-roll, Ken Burns stills, simple graphics and Hindi captions. Claude orchestrates each episode interactively (via skills in `.claude/skills/`); heavy media work runs locally through Python stages and Remotion. Full spec: `PROJECT_BRIEF.md`. How it all fits together, and why: `docs/ARCHITECTURE.md` (update it when you change a stage, the schema or a decision).

## Non-negotiable rules

- **Accuracy over automation.** Every dose, quantity, date, price, scheme detail or product name must come from a file in the episode's `sources/`. If it isn't supported, write `[VERIFY: ...]`. Nothing moves past the script stage while any `[VERIFY` remains (`pipeline.validate` enforces this).
- **Human checkpoints, never skipped:** (1) script approval, (2) draft render review, (3) final + package approval. Skip one only if the user explicitly names that checkpoint for that episode. "Just do everything" is not a skip.
- **Chemicals/pesticides:** always add a short line telling viewers to read the product label and consult their local KVK or agriculture officer. No specific brands unless the user asks.
- **Images:** Indian rural context only. No readable text inside generated images; all text the viewer reads is added in Remotion. Illegible text on notice boards, charts, bag labels and held documents is fine and realistic.
- **Every generated image is inspected** against `config.yaml: images.inspection_checklist`: for each person, 2 arms, 2 hands, 5 fingers, 2 legs, a possible posture, correct dress, tools held correctly; hands of different people never fused (zoom in on every hand-over); plus no readable text. Illegible text where real objects have it (notice boards, lab charts, bag labels, a report a farmer is holding) is realistic, so keep it; blank paper or bare institutional walls look fake. Check at full size and with zoomed crops, one image at a time, and record the result with `images --inspect`. `validate` blocks `visuals_ready` until every image passes. Never judge images from a grid.
- **People:** no real person's face, name or voice without written consent. No voice cloning.
- **Licenses:** no non-commercial models or libraries. Record every new dependency in `docs/licenses.md`.

## Audience and language

- Farmers in North India, mostly on phones; many don't read long text comfortably.
- Simple spoken Hindi (बोलचाल की हिंदी), not Sanskritized. Use the terms farmers actually say: यूरिया, DAP, स्प्रे, बीज दर.
- Tone: an experienced कृषि सलाहकार talking to a farmer. Respectful, practical, no hype, no fear-mongering.
- **Formats** (per episode, `episode.json: format`): `long` = 16:9, 3–5 min; `short` = 9:16 YouTube Short, 30–60 s (one tip, no long build-up). Scenes 6–12 s, one idea each.
- **Voices** (`config.yaml: tts.voices`, per episode via `--voice`): **rohit** (default, ~171 wpm → long ≈ 510–855 words, short ≈ 85–170) and **aman** (~191 wpm → long ≈ 570–955, short ≈ 95–190). `validate` derives the word target from the episode voice's pace.
- Structure: hook (first 10 s) → problem → explanation → steps → common mistakes → recap → CTA (`config.yaml: script.cta_hi`).

## Environment

- MacBook Air M5, **16 GB** unified memory, fanless. Run heavy jobs **one at a time**, never in parallel.
- Python 3.12 via `uv` (`uv sync`, `uv run ...`). TTS (Parler, pins transformers 4.46.1) lives in its own env `tts/` and runs as a subprocess (`tts/parler_worker.py`); the model is gated on Hugging Face, so the user must have accepted its terms and run `hf auth login`.
- Node 20+ for Remotion (`remotion/`). `ffmpeg`/`ffprobe` via Homebrew. `mflux` 0.24.0 as a uv tool; images use FLUX.2 klein 4B q4 (`mflux-generate-flux2`, about 18 s per image, peak 3.7 GB). FLUX.1 schnell q8 does not fit in 16 GB.
- Ask the user before downloading model weights > 6 GB or installing anything system-wide.
- Check a tool's CLI with `--help` before relying on flags; smoke-test and record timing in `docs/timings.md`.

## Commands

```bash
uv run python -m pipeline.new_episode <slug> [--format long|short] [--voice rohit|aman] [--date YYYY-MM-DD] [--topic "..."]
uv run python -m pipeline.text_normalize episodes/<id> [--scene N] [--force]   # build narration_spoken
uv run python -m pipeline.text_normalize --text "25 किलो DAP"                  # check one string
uv run python -m pipeline.narration episodes/<id> [--scene N] [--force] [--backend stub]
uv run python -m pipeline.tts_try --voices rohit aman                        # voice auditions / TTS smoke test
uv run python -m pipeline.images episodes/<id> [--scene N --retry --prompt "..."]   # FLUX.2 klein via mflux
uv run python -m pipeline.broll index|check|list                              # B-roll library (optional; usually empty)
uv run python -m pipeline.render episodes/<id> [--draft] [--force]            # Remotion → render/draft.mp4 | video.mp4
uv run python -m pipeline.review episodes/<id> [--draft]                      # contact sheets + checks → review/review.md
uv run python -m pipeline.package episodes/<id>                               # thumbnail.png + youtube.md from episode.json `package`
uv run python -m pipeline.validate episodes/<id>                       # check at current status
uv run python -m pipeline.validate episodes/<id> --set-status script_approved   # gate + advance
uv run python -m pipeline.<stage> episodes/<id> [--scene N] [--force]  # every stage
uv run pytest -q
cd remotion && npx tsc --noEmit                                       # typecheck compositions
cd remotion && npx remotion still src/index.ts FontTest out/font-test.png
```

## Conventions

- `episodes/<id>/episode.json` is the single source of truth; every stage reads it and writes results back (`pipeline/schema.py`, saved atomically via `pipeline.common.save_episode`).
- Status flow: draft → script_approved → narrated → visuals_ready → draft_rendered → final_rendered → reviewed → packaged. Advance status only via `validate --set-status`, which validates at the target level first.
- Stages are idempotent and per-scene: skip existing outputs unless `--force`; `--scene N` redoes one scene.
- Each stage wraps its work in `stage_timer(...)` so duration and notes land in the episode's `log.md`.
- Backends are chosen in `config.yaml`; a backend is a small function with a fixed contract (e.g. `synthesize(text, voice_cfg, out_path) -> duration_sec`) so it can move to an API or AWS without touching other stages.
- `narration_display` (captions, digits allowed) vs `narration_spoken` (sent to TTS: numbers as words, `pronunciation.yaml` fixes applied).
- All tunable values live in `config.yaml`; Remotion styling lives in `remotion/src/theme.ts` (brand colors from `assets/brand/brand.json`: primary #3fb660, dark #0a6132).
- Layout is chosen from the video size: `useTheme()` in `remotion/src/theme.ts` returns the landscape or portrait (Shorts) theme. Portrait keeps captions and graphics clear of the Shorts UI (bottom ~25%, right-side buttons).
- `remotion/src/types.ts` mirrors `pipeline/schema.py`: change both together.
- Remotion is pinned to 4.0.545. Use `trimBefore`/`trimAfter`, not the deprecated `startFrom`/`endAt`.
- Homebrew ffmpeg has no `drawtext` filter. Don't use it to put text on frames; use Pillow (as `review.py` does) or Remotion.
- Expected video length: `pipeline.common.episode_frames` mirrors `remotion/src/timing.ts` (scene = audio + padding, minus 10-frame crossfades). Change both together.
- Thumbnail text: no `-webkit-text-stroke`, because the variable Devanagari font shows stroke lines inside its glyphs. Use text-shadow.
- `episodes/2026-11-19-phase5-test*` are pipeline test episodes (fixture script, not real advice). Never publish them.
- Remotion license: free individual license (personal/educational project). Buy a Company License before any commercial use.
