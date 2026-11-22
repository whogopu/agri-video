# AgriGate Hindi Video Pipeline

Hindi educational YouTube videos for North Indian farmers: an AI narrator explains a topic over B-roll, Ken Burns stills, simple graphics and Hindi captions. Claude orchestrates each episode interactively (via skills in `.claude/skills/`); heavy media work runs locally through Python stages and Remotion. Full spec: `PROJECT_BRIEF.md`. How it all fits together, and why: `docs/ARCHITECTURE.md` (update it when you change a stage, the schema or a decision).

## Non-negotiable rules

- **Accuracy over automation.** Every dose, quantity, date, price, scheme detail or product name must come from a file in the episode's `sources/`. If it isn't supported, write `[VERIFY: ...]`. Nothing moves past the script stage while any `[VERIFY` remains (`pipeline.validate` enforces this).
- **Human checkpoints, never skipped:** (1) script approval, (2) draft render review, (3) final + package approval. Skip one only if the user explicitly names that checkpoint for that episode. "Just do everything" is not a skip.
- **Chemicals/pesticides:** always add a short line telling viewers to read the product label and consult their local KVK or agriculture officer. No specific brands unless the user asks.
- **Image prompts describe only what is there** (the klein models are prompted without a negative prompt; "no palm trees" draws palms). `images` rejects prompts with negations. Use tested phrases from `assets/visual_rules.yaml`; after every failed inspection, fix or add the rule there so the mistake doesn't come back (§7.6c).
- **Images:** Indian rural context only. No readable text inside generated images; all text the viewer reads is added in Remotion. Illegible text on notice boards, charts, bag labels and held documents is fine and realistic.
- **Every generated image is inspected** against `config.yaml: images.inspection_checklist`: for each person, 2 arms, 2 hands, 5 fingers, 2 legs, a possible posture, correct dress, tools held correctly; hands of different people never fused (zoom in on every hand-over); plus **action & physics** (trace every poured/thrown material to an open hand or tilted container, never a closed fist or upright bucket; the landing matches the action) and **narration & good practice** (the picture teaches the right thing: crop stage, method, quantity); plus no readable text. Every pass note needs `action:` (enforced by `images --inspect`; user rule 2026-11-20). Illegible text where real objects have it (notice boards, lab charts, bag labels, a report a farmer is holding) is realistic, so keep it; blank paper or bare institutional walls look fake. Check at full size and with zoomed crops, one image at a time, and record the result with `images --inspect`. `validate` blocks `visuals_ready` until every image passes. Never judge images from a grid.
- **Recurring cast, consistent faces** (user decision 2026-11-19, corrected 2026-11-20): the people on screen are recurring synthetic characters (`assets/cast/`, main farmer **रमेश जी**, lab technician सुनीता जी) so the same face and build appear in every shot, instead of a random new person each time. This is **visual only**: the script stays informative, the narrator talks directly to the viewer (what, why, how, mistakes, recap), and the characters are never named or turned into a story. Never cut content to fit a narrative. Every shot that shows a cast member is generated from his approved reference and inspected for **identity** (same face, hair, facial hair, clothes; nothing added such as a turban, cap or glasses; small rings and bangles are minor, note them and pass, user decision 2026-11-21) against `images/inspect/<shot>-vs-<id>.png`. Only the user approves a character's face (`cast approve`).
- **People:** no real person's face, name or voice without written consent. No cloning of a real person's voice. Zero-shot TTS models (e.g. Chatterbox) may only use a **synthetic** reference clip made by our own TTS (e.g. a Parler Rohit take); user decision 2026-11-19.
- **Licenses:** no non-commercial models or libraries. Record every new dependency in `docs/licenses.md`.

## Audience and language

- Farmers in North India, mostly on phones; many don't read long text comfortably.
- Simple spoken Hindi (बोलचाल की हिंदी), not Sanskritized. Use the terms farmers actually say: यूरिया, DAP, स्प्रे, बीज दर.
- Tone: an experienced कृषि सलाहकार talking to a farmer. Respectful, practical, no hype, no fear-mongering.
- **Formats** (per episode, `episode.json: format`): `long` = 16:9, 3–5 min; `short` = 9:16 YouTube Short, 30–60 s (one tip, no long build-up). Scenes 6–12 s, one idea each.
- **Voices** (`config.yaml: tts.voices`, per episode via `--voice`), chosen by the user 2026-11-19 after a 5-model listening test: **maya_vasant** = male (default; Maya2 Native, ~174 wpm → long ≈ 520–870 words, short ≈ 87–174) and **veena_varun** = female (Veena, ~176 wpm; the name is misleading, it is a female voice). Older Parler voices rohit/aman and test-only candidates (chatterbox_rohit, indic_speak_amit, maya_satvik/abhay, veena_agastya) remain in config. `validate` derives the word target from the episode voice's pace.
- Structure: hook (first 10 s) → problem → explanation → steps → common mistakes → recap → CTA (`config.yaml: script.cta_hi`).

## Environment

- MacBook Air M5, **16 GB** unified memory, fanless. Run heavy jobs **one at a time**, never in parallel.
- Python 3.12 via `uv` (`uv sync`, `uv run ...`). Isolated envs, each called as a subprocess with JSON in/out: `tts-mlx/` (production voices: mlx-audio for Maya2, `snac_lm_worker.py` for Veena/Indic-Speak), `tts/` (Parler, pins transformers 4.46.1; gated model, needs `hf auth login`), `asr/` (mlx-whisper + librosa, scores narration takes).
- Node 20+ for Remotion (`remotion/`). `ffmpeg`/`ffprobe` via Homebrew. `mflux` 0.24.0 as a uv tool; images use FLUX.3 Image Klein q8 (`mflux-generate-flux3`, about 2 min per image, peak 7.8 GB; cast shots `mflux-generate-flux3-edit` with head-crop references, about 3 min, 9 GB), chosen 2026-11-22 by blind bake-off (`bakeoff/report.md`). Its FLUX Kommunity License is valid only below US$5M gross annual revenue. FLUX.1 schnell q8 does not fit in 16 GB.
- Ask the user before downloading model weights > 6 GB or installing anything system-wide.
- Check a tool's CLI with `--help` before relying on flags; smoke-test and record timing in `docs/timings.md`.

## Commands

```bash
uv run python -m pipeline.new_episode <slug> [--format long|short] [--voice maya_vasant|veena_varun] [--date YYYY-MM-DD] [--topic "..."]
uv run python -m pipeline.text_normalize episodes/<id> [--scene N] [--force]   # build narration_spoken
uv run python -m pipeline.text_normalize --text "25 किलो DAP"                  # check one string
uv run python -m pipeline.narration episodes/<id> [--scene N] [--force] [--takes N] [--backend stub]   # sentence takes, best picked
uv run python -m pipeline.narration episodes/<id> --pick 9:2:3                # override: scene 9, segment 2 → take 3
uv run python -m pipeline.tts_try --voices rohit aman                        # voice auditions / TTS smoke test
uv run python -m pipeline.cast list | new <id> ... | candidates <id> | sheet <id> | approve <id> N   # recurring characters; approve ONLY after the user picks
uv run python -m pipeline.images episodes/<id> [--scene N --shot K --retry --prompt "..."]   # FLUX.3 Klein via mflux (edit mode with cast references)
uv run python -m pipeline.visual_rules --list | --lint "prompt"              # tested prompt phrases ({kind:key}) + lint (no negations)
uv run python -m pipeline.images episodes/<id> --scene N --shot K --checklist  # checklist + this shot's must-show items
uv run python -m pipeline.images episodes/<id> --scene N --shot K --spec f.yaml [--dry-run]  # shot from a scene spec (pipeline/scene_spec.py)
uv run python -m pipeline.broll index|check|list                              # B-roll library (optional; usually empty)
uv run python -m pipeline.render episodes/<id> [--draft] [--force]            # Remotion → render/draft.mp4 | video.mp4
uv run python -m pipeline.review episodes/<id> [--draft]                      # contact sheets + checks → review/review.md
uv run python -m pipeline.package episodes/<id>                               # thumbnail.png + youtube.md from episode.json `package`
uv run python -m pipeline.validate episodes/<id>                       # check at current status
uv run python -m pipeline.validate episodes/<id> --set-status script_approved   # gate + advance
uv run python -m pipeline.<stage> episodes/<id> [--scene N] [--force]  # every stage
uv run python -m dashboard                                             # control room → http://127.0.0.1:8765 (run/stop/retry stages, progress, ETA)
uv run pytest -q
cd remotion && npx tsc --noEmit                                       # typecheck compositions
cd remotion && npx remotion still src/index.ts FontTest out/font-test.png
```

## Conventions

- Image scenes hold several **shots** (`visual.shots[]`, schema v2), each starting at a narration sentence (`at_segment`); v1 files migrate on load. A shot has a free-text `image_prompt` or a structured `spec` (slots in `bakeoff/shots.yaml`), never both; specs are linted and rendered into the prompt in code. `pipeline.common.shot_starts_sec` mirrors `remotion/src/timing.ts: shotStartFrames`: change both together.
- `episodes/<id>/episode.json` is the single source of truth; every stage reads it and writes results back (`pipeline/schema.py`, saved atomically via `pipeline.common.save_episode`).
- Status flow: draft → script_approved → narrated → visuals_ready → draft_rendered → final_rendered → reviewed → packaged. Advance status only via `validate --set-status`, which validates at the target level first.
- Stages are idempotent and per-scene: skip existing outputs unless `--force`; `--scene N` redoes one scene.
- Each stage wraps its work in `stage_timer(...)` so duration and notes land in the episode's `log.md`.
- Backends are chosen in `config.yaml`; a backend is a small function with a fixed contract (e.g. `synthesize(text, voice_cfg, out_path) -> duration_sec`) so it can move to an API or AWS without touching other stages.
- `narration_display` (captions, digits allowed) vs `narration_spoken` (sent to TTS: numbers as words, `pronunciation.yaml` fixes applied).
- Delivery markup in narration: `|` breath, `||` long pause, `{slow|warm|firm|question}` sentence style (`pipeline/prosody.py`). Stripped for captions/word counts; must survive into `narration_spoken`. Narration is synthesized per sentence with several takes, scored by Whisper in the isolated `asr/` env (`pipeline/take_scoring.py`); `audio/takes.md` lists every take.
- All tunable values live in `config.yaml`; Remotion styling lives in `remotion/src/theme.ts` (brand colors from `assets/brand/brand.json`: primary #3fb660, dark #0a6132).
- Layout is chosen from the video size: `useTheme()` in `remotion/src/theme.ts` returns the landscape or portrait (Shorts) theme. Portrait keeps captions and graphics clear of the Shorts UI (bottom ~25%, right-side buttons).
- `remotion/src/types.ts` mirrors `pipeline/schema.py`: change both together.
- Remotion is pinned to 4.0.545. Use `trimBefore`/`trimAfter`, not the deprecated `startFrom`/`endAt`.
- Homebrew ffmpeg has no `drawtext` filter. Don't use it to put text on frames; use Pillow (as `review.py` does) or Remotion.
- Expected video length: `pipeline.common.episode_frames` mirrors `remotion/src/timing.ts` (scene = lead-in + audio + padding, minus 10-frame crossfades; narration starts after the lead-in). Change both together.
- Thumbnail text: no `-webkit-text-stroke`, because the variable Devanagari font shows stroke lines inside its glyphs. Use text-shadow.
- `episodes/2026-11-19-phase5-test*` are pipeline test episodes (fixture script, not real advice). Never publish them.
- Remotion license: free individual license (personal/educational project). Buy a Company License before any commercial use.
